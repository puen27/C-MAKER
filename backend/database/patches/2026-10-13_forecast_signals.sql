-- 2026-10-13 기상청 예보 신호 + 신호별 명부 상한 (테이블 구조 변경 없음, 여러 번 실행해도 안전)
--
-- 실행: psql -U myapp_user -d myapp_db -v ON_ERROR_STOP=1 -f backend/database/patches/2026-10-13_forecast_signals.sql
--
-- 1) 예보 신호 4종 임계치 + 신호별 명부 상한(SIGNAL_SHARE_CAP_PCT) 행 추가
-- 2) 예보 신호 가중치 초기값 추가
-- 3) 지점당 일일 이벤트 상한 8 → 12 (본부가 이미 다른 값으로 바꿨다면 건드리지 않는다), 감사 로그 기록

BEGIN;
SET LOCAL search_path TO cmaker;

INSERT INTO threshold_config (signal_type, category, label, description, threshold_value, unit,
                              is_fixed, integer_only, min_value, max_value)
VALUES
    ('TEMP_SHIFT_FORECAST',   'SIGNAL', '기온 급변 예보',
     '내일·모레 최저 또는 최고기온이 오늘보다 기준을 초과해 달라질 것으로 예보되면 승격한다(기상청 단기예보, 예보 대상일까지 반영)',
     5, '°C', FALSE, FALSE, 0, 30),
    ('SEASON_SHIFT_FORECAST', 'SIGNAL', '계절 전환 예보',
     '5일 이후 평균 최저기온이 오늘~3일 뒤 평균보다 기준을 초과해 달라질 것으로 예보되면 승격한다(기상청 중기·단기예보)',
     4, '°C', FALSE, FALSE, 0, 30),
    ('FIRST_FREEZE_FORECAST', 'SIGNAL', '첫 영하 예보',
     '9월 이후 시즌 첫 최저기온 영하 예보 시 즉시 승격한다(고정). 시즌에 1번만 승격하고 예보 대상일까지 반영',
     0, '건', TRUE, TRUE, NULL, NULL),
    ('FIRST_HEAT_FORECAST',   'SIGNAL', '첫 폭염 예보',
     '5월 이후 시즌 첫 최고기온 33°C 이상 예보 시 즉시 승격한다(고정). 시즌에 1번만 승격하고 예보 대상일까지 반영',
     0, '건', TRUE, TRUE, NULL, NULL),
    ('SIGNAL_SHARE_CAP_PCT',  'SYSTEM', '신호별 명부 상한',
     '주 사유가 상권·거시 신호(환율·유가·특보·기상 예보)인 추천은 한 종류당 명부의 이 비율까지만 싣는다. 넘치는 자리는 다음 순위로 채운다',
     30, '%', FALSE, FALSE, 5, 100)
ON CONFLICT (signal_type) DO NOTHING;

INSERT INTO signal_weight (signal_type, industry_code, weight, base_weight)
VALUES ('TEMP_SHIFT_FORECAST',   '*', 0.6, 0.6),
       ('SEASON_SHIFT_FORECAST', '*', 0.7, 0.7),
       ('FIRST_FREEZE_FORECAST', '*', 0.8, 0.8),
       ('FIRST_HEAT_FORECAST',   '*', 0.8, 0.8)
ON CONFLICT (signal_type, industry_code) DO NOTHING;

WITH changed AS (
    UPDATE threshold_config
       SET threshold_value = 12, updated_at = now()
     WHERE signal_type = 'DAILY_EVENT_CAP' AND threshold_value = 8
    RETURNING id
)
INSERT INTO audit_log (actor_user_id, action, entity_type, entity_id, before_value, after_value)
SELECT NULL, 'THRESHOLD_UPDATED', 'threshold_config', id::text,
       '{"threshold_value": 8, "unit": "건", "via": "patch 2026-10-13_forecast_signals"}'::jsonb,
       '{"threshold_value": 12, "unit": "건"}'::jsonb
FROM changed;

COMMIT;
