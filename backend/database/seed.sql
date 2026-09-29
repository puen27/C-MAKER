-- =====================================================================
-- C-MAKER 초기 데이터 (docs/10-implementation-guide.md §7.4)
--   BRANCH + USER(app_user) + THRESHOLD_CONFIG (+ SIGNAL_WEIGHT 초기 가중치)
--
-- 실행 (초기 비밀번호는 저장소에 남기지 않도록 psql 변수로 넘긴다):
--   psql -U myapp_user -d myapp_db -v initial_password='<초기 비밀번호>' -f backend/database/seed.sql
--
-- ⚠ 아래 지점·계정은 파일럿 온보딩용 예시다. 실제 파일럿 지점 값으로 바꿔서 실행한다.
-- ⚠ app_user.password는 결정 사항(docs/db-schema-decisions-review.md)에 따라 평문으로 저장된다.
--   운영 전환 전 보안팀 검토를 권장한다.
-- =====================================================================

\if :{?initial_password}
\else
    \echo 'initial_password 변수가 필요합니다: psql ... -v initial_password=''<비밀번호>'' -f seed.sql'
    \quit
\endif

SET search_path TO cmaker;

BEGIN;

-- ── 지점 (좌표는 geocode_job이 채운다, effective_from은 트리거가 다음 날 07:30으로 설정) ──
INSERT INTO branch (branch_code, name, address, coverage_radius_km, primary_industry_tags, handles_forex, atm_count)
VALUES ('000101', '강남중앙지점', '서울특별시 강남구 테헤란로 152', 1.5, '음식,소매,미용', TRUE, 4)
ON CONFLICT (branch_code) DO NOTHING;

-- ── 계정 (RM·지점장은 소속 지점 필수, 본부는 NULL — CONST-03) ──
INSERT INTO app_user (branch_id, username, name, role, password, session_timeout_minutes, session_extendable)
SELECT b.id, v.username, v.name, v.role, :'initial_password', v.timeout, v.extendable
FROM (VALUES
        ('rm01',      '김도윤', 'RM',             30, TRUE),
        ('manager01', '한서영', 'BRANCH_MANAGER', 30, TRUE)
     ) AS v(username, name, role, timeout, extendable)
JOIN branch b ON b.branch_code = '000101'
ON CONFLICT (username) DO NOTHING;

INSERT INTO app_user (branch_id, username, name, role, password, session_timeout_minutes, session_extendable)
VALUES (NULL, 'hqmkt01', '최유나', 'HQ_MARKETING',  :'initial_password', 30, TRUE),
       (NULL, 'hqcmp01', '정민재', 'HQ_COMPLIANCE', :'initial_password', 30, TRUE)
ON CONFLICT (username) DO NOTHING;

-- ── 임계치·운영 파라미터 초기값 (없으면 배치 판정이 동작하지 않는다) ──
-- 승격 판정은 raw_value > threshold_value (도메인 정의서 5.1절 "초과")
INSERT INTO threshold_config (signal_type, category, label, description, threshold_value, unit,
                              is_fixed, integer_only, min_value, max_value)
VALUES
    ('NEW_BUSINESS_OPENING',  'SIGNAL', '신규 개업(사업체)',
     '담당 반경 내 최근 인허가된 신규 개업 사업체 1건마다 사업체 단위 신호로 승격한다(발생 즉시, 고정)',
     0, '건', TRUE, TRUE, NULL, NULL),
    ('AREA_NEW_OPENINGS',     'SIGNAL', '신규 개업(상권)',
     '담당 반경 내 당일 신규 개업 건수가 기준을 초과하면 상권 단위 신호로 승격한다',
     3, '건/일', FALSE, TRUE, 0, 1000),
    ('INDUSTRY_NEW_OPENINGS', 'SIGNAL', '신규 개업(동일 업종)',
     '담당 반경 내 같은 업종의 당일 신규 개업 건수가 기준을 초과하면 업종 단위 신호로 승격한다',
     1, '건/일', FALSE, TRUE, 0, 1000),
    ('FX_DAILY_CHANGE',       'SIGNAL', '환율 일변동',
     '원/달러 매매기준율 전일 대비 변동률(절댓값)',
     1.0, '%', FALSE, FALSE, 0, 100),
    ('OIL_PRICE_CHANGE',      'SIGNAL', '유가 일변동',
     '지점 소재 시도 평균 휘발유 가격 전일 대비 변동률(절댓값)',
     0.5, '%', FALSE, FALSE, 0, 100),
    ('WEATHER_WARNING',       'SIGNAL', '기상특보',
     '지점 관할 기상특보 발효 즉시 승격한다(고정). 해제는 신호 원장에만 저장한다',
     0, '건', TRUE, TRUE, NULL, NULL),
    ('EVENT_COOLDOWN_DAYS',   'SYSTEM', '이벤트 병합 쿨다운',
     '동일 대상·동일 신호가 이 기간 안에 재발하면 기존 이벤트에 병합한다(RULE-SENSE-01)',
     14, '일', FALSE, TRUE, 1, 90),
    ('DAILY_EVENT_CAP',       'SYSTEM', '지점당 일일 이벤트 상한',
     '초과분은 점수 순으로 절사하고 "외 N건"으로만 표시한다(RULE-SENSE-02)',
     8, '건', FALSE, TRUE, 1, 50),
    ('CONTACT_COOLDOWN_DAYS', 'SYSTEM', '최근 접촉 쿨다운',
     '방문함 태깅 후 이 기간 동안 명부에서 배제한다(RULE-TARGET-01)',
     30, '일', FALSE, TRUE, 0, 365),
    ('AREA_REASON_RATIO_LIMIT', 'SYSTEM', '상권사유비율 경고 기준',
     '상권 사유만 가진 항목 비율이 기준을 초과하면 명부 상단에 표시한다(RULE-TARGET-06)',
     60, '%', FALSE, FALSE, 0, 100)
ON CONFLICT (signal_type) DO NOTHING;

-- ── 신호 가중치 초기값 w₀ (콜드 스타트 60일 고정, CLAUDE.md §4 — MVP는 갱신 비활성) ──
INSERT INTO signal_weight (signal_type, industry_code, weight, base_weight)
VALUES ('NEW_BUSINESS_OPENING',  '*', 1.5, 1.5),
       ('INDUSTRY_NEW_OPENINGS', '*', 1.0, 1.0),
       ('AREA_NEW_OPENINGS',     '*', 0.6, 0.6),
       ('FX_DAILY_CHANGE',       '*', 0.8, 0.8),
       ('OIL_PRICE_CHANGE',      '*', 0.8, 0.8),
       ('WEATHER_WARNING',       '*', 0.5, 0.5)
ON CONFLICT (signal_type, industry_code) DO NOTHING;

COMMIT;
