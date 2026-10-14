-- C-MAKER 운영 데이터 품질 점검 (읽기 전용 — INSERT/UPDATE/DELETE 없음, 여러 번 실행해도 안전)
--
-- 실행: psql -U myapp_user -d myapp_db -f backend/database/checks/data_quality.sql > dq_$(date +%Y%m%d).txt
--
-- 각 항목 제목의 [정상값]이 기대값이다. 결과가 다르면 그 항목을 들여다본다.
-- 최초 실행 결과와 판단 근거: 2026-10-14 데이터 검증(계정 비밀번호 동일·평문, 같은 건물 쏠림, 지난 환율 인용 등).
-- 비밀번호는 값을 출력하지 않고 집계만 한다.

\pset pager off
SET search_path TO cmaker;

\echo
\echo ######## [R] 명부 (recommendation) ########

\echo == R1 지점·일자별 건수/순위 구멍 [정상값: 0행. same_address_cap 때문에 20건 미만은 허용] ==
SELECT branch_id, recommended_on, count(*) AS n, max(rank_in_branch) AS max_rk
FROM recommendation GROUP BY 1, 2
HAVING count(*) > 20 OR max(rank_in_branch) <> count(*) ORDER BY 2, 1;

\echo == R2 점수 재계산 불일치 [정상값: mismatch 0] ==
SELECT count(*) FILTER (WHERE abs(score - (signal_score + freshness_score) * proximity * scale_fit) > 0.01) AS mismatch,
       round(max(abs(score - (signal_score + freshness_score) * proximity * scale_fit)), 4) AS max_diff
FROM recommendation;

\echo == R3 같은 건물(쉼표 앞 도로명주소) 3곳 이상 — 최근 7일 [정상값: 0행, RULE-TARGET-08 same_address_cap=2] ==
WITH k AS (
  SELECT r.branch_id, r.recommended_on,
         btrim(regexp_replace(regexp_replace(split_part(b.address, ',', 1), '\([^)]*\)', ' ', 'g'), '\s+', ' ', 'g')) AS bkey
  FROM recommendation r JOIN business b ON b.id = r.business_id
  WHERE b.address IS NOT NULL AND r.recommended_on >= current_date - 6)
SELECT branch_id, recommended_on, left(bkey, 40) AS building, count(*) AS n
FROM k GROUP BY 1, 2, 3 HAVING count(*) >= 3 ORDER BY 2 DESC, 4 DESC;

\echo == R4 같은 날 같은 가게 중복(같은 건물 + 같은 상호) — 최근 7일 [정상값: 0행] ==
WITH k AS (
  SELECT r.branch_id, r.recommended_on, lower(regexp_replace(b.name, '\s', '', 'g')) AS nkey,
         btrim(regexp_replace(regexp_replace(split_part(b.address, ',', 1), '\([^)]*\)', ' ', 'g'), '\s+', ' ', 'g')) AS bkey
  FROM recommendation r JOIN business b ON b.id = r.business_id
  WHERE r.recommended_on >= current_date - 6)
SELECT branch_id, recommended_on, left(nkey, 20) AS name, count(*) AS n FROM k
GROUP BY 1, 2, 3, bkey HAVING count(*) > 1 ORDER BY 2 DESC;

\echo == R5 휴·폐업 사업장 추천 [정상값: 0행] ==
SELECT r.recommended_on, b.operating_status, count(*) AS n
FROM recommendation r JOIN business b ON b.id = r.business_id
WHERE b.operating_status <> '정상' AND b.status_checked_at <= r.recommended_on
GROUP BY 1, 2 ORDER BY 1, 2;

\echo == R6 배제 규칙 위반: 방문함 30일 내 / 영구 부적합 재추천 [정상값: 0행] ==
SELECT t.tag_value, t.reject_reason, count(*) AS re_recommended
FROM tag_feedback t
JOIN recommendation r1 ON r1.id = t.recommendation_id
JOIN recommendation r2 ON r2.business_id = r1.business_id AND r2.branch_id = r1.branch_id
 AND r2.recommended_on > (t.tagged_at AT TIME ZONE 'Asia/Seoul')::date
WHERE (t.tag_value = 'VISITED' AND r2.recommended_on < (t.tagged_at AT TIME ZONE 'Asia/Seoul')::date + 30)
   OR (t.tag_value = 'REJECTED' AND t.reject_reason IN ('ALREADY_CUSTOMER', 'NOT_TARGET', 'UNREACHABLE'))
GROUP BY 1, 2;

\echo == R7 상호 없는 사업장 추천(INVALID_NAME) — 최근 7일 [정상값: 0] ==
SELECT count(*) AS invalid_name_recs
FROM recommendation r JOIN business b ON b.id = r.business_id
WHERE r.recommended_on >= current_date - 6
  AND (regexp_replace(b.name, '\s', '', 'g') LIKE '업소명없음%'
       OR regexp_replace(b.name, '\s', '', 'g') = ANY (
            SELECT regexp_replace(part, '\s', '', 'g') FROM unnest(string_to_array(b.industry_name, '·')) part));

\echo == R8 같은 사업장 반복 노출 상위 [참고: 신규 개업 사업장은 반영 기간(7일) 동안 반복될 수 있음] ==
SELECT r.branch_id, r.business_id, left(b.name, 18) AS name, count(*) AS days, min(r.recommended_on), max(r.recommended_on)
FROM recommendation r JOIN business b ON b.id = r.business_id
WHERE r.recommended_on >= current_date - 13
GROUP BY 1, 2, 3 HAVING count(*) >= 5 ORDER BY days DESC LIMIT 10;

\echo == R9 연결 무결성 [정상값: 전부 0] ==
SELECT
  (SELECT count(*) FROM recommendation r WHERE NOT EXISTS (SELECT 1 FROM brief b WHERE b.recommendation_id = r.id)) AS rec_no_brief,
  (SELECT count(*) FROM recommendation r WHERE r.reason_tier <> 'AREA'
     AND NOT EXISTS (SELECT 1 FROM recommendation_event re WHERE re.recommendation_id = r.id)) AS nonarea_no_event,
  (SELECT count(*) FROM recommendation_event re JOIN recommendation r ON r.id = re.recommendation_id
     JOIN event e ON e.id = re.event_id WHERE e.branch_id <> r.branch_id) AS event_other_branch,
  (SELECT count(*) FROM recommendation r JOIN batch_run b ON b.id = r.batch_run_id WHERE b.target_date <> r.recommended_on) AS run_date_mismatch;

\echo
\echo ######## [F] 브리프 ########

\echo == F1 생성 상태·검증 오류·지연 [참고: TEMPLATE은 LLM 장애 시 폴백] ==
SELECT generation_status, count(*) AS n,
       count(*) FILTER (WHERE validation_errors <> '[]'::jsonb) AS has_verr,
       count(*) FILTER (WHERE btrim(talk_script) = '') AS empty_script,
       count(*) FILTER (WHERE jsonb_array_length(reason_facts) = 0) AS no_facts,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms, max(latency_ms) AS max_ms
FROM brief GROUP BY 1;

\echo == F2 검증 오류 종류 상위 ==
SELECT e AS validation_error, count(*) FROM brief, jsonb_array_elements_text(validation_errors) e
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

\echo == F3 지난 거시 이벤트 인용 — 명부일에 같은 대상의 더 새로운 신호가 있는데 그 이벤트가 사유로 쓰임 [정상값: 0행, superseded_signal_types] ==
SELECT r.recommended_on, e.signal_type, count(DISTINCT r.id) AS recs
FROM recommendation r
JOIN recommendation_event re ON re.recommendation_id = r.id
JOIN event e ON e.id = re.event_id
WHERE e.signal_type IN ('FX_DAILY_CHANGE', 'OIL_PRICE_CHANGE', 'WEATHER_WARNING')
  AND EXISTS (
    SELECT 1 FROM signal newer
    WHERE newer.branch_id = e.branch_id AND newer.signal_type = e.signal_type AND newer.target_key = e.target_key
      AND newer.as_of_date <= r.recommended_on
      AND newer.as_of_date > (SELECT max(s.as_of_date) FROM signal s WHERE s.event_id = e.id AND s.as_of_date <= r.recommended_on))
GROUP BY 1, 2 ORDER BY 1 DESC, 2;

\echo
\echo ######## [S] 신호·이벤트·수집 ########

\echo == S1 신호 유형별 기준일 지연·승격 정합성(현재 임계치 기준) [정상값: over_th_not_promoted·promoted_under_th 0] ==
SELECT s.signal_type, count(*) AS n,
       max(br.target_date - s.as_of_date) AS max_lag_days,
       count(*) FILTER (WHERE s.event_id IS NOT NULL) AS promoted,
       count(*) FILTER (WHERE s.raw_value > t.threshold_value AND s.event_id IS NULL AND NOT t.is_fixed) AS over_th_not_promoted,
       count(*) FILTER (WHERE s.raw_value <= t.threshold_value AND s.event_id IS NOT NULL AND NOT t.is_fixed) AS promoted_under_th
FROM signal s LEFT JOIN batch_run br ON br.id = s.batch_run_id LEFT JOIN threshold_config t ON t.signal_type = s.signal_type
GROUP BY 1 ORDER BY 1;

\echo == S2 사업체 이벤트 대상이 휴·폐업 또는 없음 [정상값: 0행] ==
SELECT e.id, e.branch_id, e.target_key, b.operating_status
FROM event e LEFT JOIN business b ON 'BUSINESS:' || b.id = e.target_key
WHERE e.scope = 'BUSINESS' AND e.status = 'ACTIVE' AND (b.id IS NULL OR b.operating_status <> '정상');

\echo == S3 최근 배치 소스 상태 — 최근 7회 [참고: UNAVAILABLE·지연(delay_days>0) 확인] ==
SELECT b.id AS run_id, b.target_date, x ->> 'source_name' AS source, x ->> 'status' AS status,
       x ->> 'as_of_date' AS as_of, x ->> 'delay_days' AS delay, left(x ->> 'error', 50) AS error
FROM (SELECT * FROM batch_run ORDER BY id DESC LIMIT 7) b, jsonb_array_elements(b.source_status) x
WHERE x ->> 'status' <> 'FRESH' OR coalesce((x ->> 'delay_days')::int, 0) > 0
ORDER BY b.id DESC, source;

\echo
\echo ######## [B] 모집단 (business) ########

\echo == B1 출처·상태별 결측 [참고: SBIZ는 원천에 인허가일이 없어 no_licensed = n이 정상] ==
SELECT status_source, operating_status, count(*) AS n,
       count(*) FILTER (WHERE licensed_on IS NULL) AS no_licensed,
       count(*) FILTER (WHERE address IS NULL OR btrim(address) = '') AS no_addr,
       count(*) FILTER (WHERE industry_code = '' OR industry_name = '') AS no_industry
FROM business GROUP BY 1, 2 ORDER BY 1, 2;

\echo == B2 상호 품질(정상 영업) [참고: 명부에서는 INVALID_NAME으로 배제됨] ==
SELECT count(*) FILTER (WHERE regexp_replace(name, '\s', '', 'g') LIKE '업소명없음%') AS no_name,
       count(*) FILTER (WHERE regexp_replace(name, '\s', '', 'g') = ANY (
            SELECT regexp_replace(part, '\s', '', 'g') FROM unnest(string_to_array(industry_name, '·')) part)) AS industry_as_name,
       count(*) FILTER (WHERE char_length(btrim(name)) <= 1) AS one_char
FROM business WHERE operating_status = '정상';

\echo == B3 같은 좌표 20곳 이상 클러스터 [참고: 건물 단위 좌표] ==
SELECT count(*) AS clusters_ge20, sum(cnt) AS businesses
FROM (SELECT count(*) cnt FROM business WHERE operating_status = '정상' GROUP BY lat, lng HAVING count(*) >= 20) x;

\echo
\echo ######## [T] 태깅·감사·계정·지점 ########

\echo == T1 태깅 권한·시점 [정상값: 전부 0] ==
SELECT count(*) FILTER (WHERE u.branch_id IS DISTINCT FROM r.branch_id) AS tagger_other_branch,
       count(*) FILTER (WHERE t.tagged_at < r.created_at) AS tagged_before_rec,
       count(*) FILTER (WHERE u.is_active = false) AS inactive_tagger
FROM tag_feedback t JOIN app_user u ON u.id = t.tagged_by JOIN recommendation r ON r.id = t.recommendation_id;

\echo == T2 감사로그 vs 태깅 [정상값: 전부 0] ==
WITH last AS (
  SELECT DISTINCT ON (entity_id) entity_id, action FROM audit_log
  WHERE entity_type = 'recommendation' AND action IN ('TAG_SAVED', 'TAG_REVERTED') ORDER BY entity_id, created_at DESC, id DESC)
SELECT count(*) FILTER (WHERE action = 'TAG_SAVED'
         AND NOT EXISTS (SELECT 1 FROM tag_feedback t WHERE t.recommendation_id::text = last.entity_id)) AS saved_but_missing,
       count(*) FILTER (WHERE action = 'TAG_REVERTED'
         AND EXISTS (SELECT 1 FROM tag_feedback t WHERE t.recommendation_id::text = last.entity_id)) AS reverted_but_exists,
       (SELECT count(*) FROM tag_feedback t WHERE NOT EXISTS (
          SELECT 1 FROM audit_log a WHERE a.entity_type = 'recommendation' AND a.entity_id = t.recommendation_id::text)) AS tag_without_audit
FROM last;

\echo == T3 계정 비밀번호 저장 형태 — 값은 출력하지 않음 [정상값: hashed = users, distinct_passwords = users] ==
SELECT count(*) AS users,
       count(*) FILTER (WHERE password ~ '^\$2[aby]\$' OR password ~ '^\$argon2' OR password ~ '^pbkdf2') AS hashed,
       count(DISTINCT password) AS distinct_passwords
FROM app_user;

\echo == T4 지점 이력 0길이 구간 [정상값: 2026-10-14 패치 이후 recorded_at인 행 0] ==
SELECT count(*) AS zero_intervals, max(recorded_at) AS latest_recorded
FROM branch_history WHERE valid_from >= valid_until;
