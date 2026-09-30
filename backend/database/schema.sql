-- =====================================================================
-- C-MAKER 데이터베이스 스키마 (OPS-09: 단일 파일, psql로 직접 실행)
-- 기준: docs/6-erd.md v1.4.0, docs/10-implementation-guide.md v2.2.0 §7
--
-- 적용:  psql -U myapp_user -d myapp_db -f backend/database/schema.sql
--
-- ERD 대비 구현상 변경점 (전부 주석으로 근거를 남김)
--  * 전용 스키마 `cmaker` 사용 — 공유 DB(myapp_db)의 기존 테이블과 이름 충돌 방지(10번 문서 §4 주의사항)
--  * USER → app_user — PostgreSQL 예약어 회피. 로그인 아이디 컬럼 username 추가(ERD에 없음)
--  * SIGNAL/EVENT에 target_key·raw_value·unit·as_of_date 등 추가 — 5.1절 "동일 대상·동일 신호종류"
--    판정과 VAL-09(이벤트 기준일 필수)를 스키마로 표현하기 위함
--  * BUSINESS에 sbiz_store_id·industry_name·address 추가 — S-1 상가정보 모집단(10번 문서 §5.1) 병합키
--  * BRIEF·RECOMMENDATION·BATCH_RUN에 감사 추적 컬럼 추가 — CLAUDE.md §6(입력 신호·프롬프트·모델 버전·출력 보존)
--  * audit_log 신설 — REQ-15 감사 추적(태깅·임계치 변경·배치 재실행·CRM 다운로드 이력)
--  * Phase 2·3 전용 테이블(OPERATION_FORECAST, CAMPAIGN 계열)은 MVP 범위 밖이라 생성하지 않는다(7번 문서)
--  * 시각 컬럼은 TIMESTAMPTZ로 저장하고, 업무 기준 시각(익일 07:30)은 Asia/Seoul로 계산한다
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS cmaker;
SET search_path TO cmaker;

-- ---------------------------------------------------------------------
-- 1. branch — 영업점 (운영자가 psql로 직접 INSERT/UPDATE, REQ-01)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS branch (
    id                    SERIAL PRIMARY KEY,
    branch_code           VARCHAR(6)   NOT NULL UNIQUE,
    name                  VARCHAR(100) NOT NULL,
    address               VARCHAR(300) NOT NULL,
    lat                   NUMERIC(10,7),               -- nullable, geocode_job이 채움(RULE-BRANCH-03)
    lng                   NUMERIC(10,7),
    geocoded_address      VARCHAR(300),                -- 좌표를 산출한 주소(주소 변경 감지용)
    coverage_radius_km    NUMERIC(3,1) NOT NULL,
    primary_industry_tags VARCHAR(300) NOT NULL DEFAULT '',  -- 쉼표 구분 주력 업종 키워드
    handles_forex         BOOLEAN      NOT NULL DEFAULT FALSE,
    atm_count             INT          NOT NULL DEFAULT 0,
    effective_from        TIMESTAMPTZ  NOT NULL,       -- 트리거가 자동 설정(CONST-19)
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT branch_code_format CHECK (branch_code ~ '^[0-9]{6}$'),                      -- VAL-01 / CONST-01
    CONSTRAINT branch_radius_range CHECK (coverage_radius_km BETWEEN 0.5 AND 3.0),         -- VAL-02 / CONST-02
    CONSTRAINT branch_atm_count_nonneg CHECK (atm_count >= 0)
);

-- ---------------------------------------------------------------------
-- 2. branch_history — 지점 변경 이력 (RULE-BRANCH-01 익일 반영)
--    [valid_from, valid_until) 구간에 유효했던 값. valid_from = 변경 전 BRANCH.effective_from
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS branch_history (
    id                    SERIAL PRIMARY KEY,
    branch_id             INT          NOT NULL REFERENCES branch(id),
    name                  VARCHAR(100) NOT NULL,
    address               VARCHAR(300) NOT NULL,
    lat                   NUMERIC(10,7),
    lng                   NUMERIC(10,7),
    coverage_radius_km    NUMERIC(3,1) NOT NULL,
    primary_industry_tags VARCHAR(300) NOT NULL,
    handles_forex         BOOLEAN      NOT NULL,
    atm_count             INT          NOT NULL,
    valid_from            TIMESTAMPTZ  NOT NULL,
    valid_until           TIMESTAMPTZ  NOT NULL,
    recorded_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_branch_history_branch ON branch_history(branch_id, valid_until);

-- CONST-19: INSERT/UPDATE 시 effective_from을 "다음 날 07:30(KST)"으로 설정하고,
-- UPDATE로 추적 대상 값이 바뀌면 변경 전 값을 branch_history로 옮긴다.
--
-- SET search_path (함수 정의 하단): 함수 본문의 미수식 테이블명(branch_history)이 항상 cmaker로
-- 해석되도록 고정한다. 이 지정이 없으면 호출 세션의 search_path를 따르므로, 운영자가 psql에서
-- 기본 search_path("$user", public)로 접속해 UPDATE하면 공유 DB의 public.branch_history를
-- 가리켜 실패한다(실제 발생). 앱 커넥션은 pool.py가 -c search_path=cmaker로 열어 무관했다.
CREATE OR REPLACE FUNCTION branch_apply_effective_from() RETURNS trigger AS $$
DECLARE
    next_effective TIMESTAMPTZ :=
        (((now() AT TIME ZONE 'Asia/Seoul')::date + 1) + TIME '07:30') AT TIME ZONE 'Asia/Seoul';
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.effective_from := next_effective;
        NEW.updated_at := now();
        RETURN NEW;
    END IF;

    IF (NEW.name, NEW.address, NEW.lat, NEW.lng, NEW.coverage_radius_km,
        NEW.primary_industry_tags, NEW.handles_forex, NEW.atm_count)
       IS DISTINCT FROM
       (OLD.name, OLD.address, OLD.lat, OLD.lng, OLD.coverage_radius_km,
        OLD.primary_industry_tags, OLD.handles_forex, OLD.atm_count) THEN
        INSERT INTO branch_history (branch_id, name, address, lat, lng, coverage_radius_km,
                                    primary_industry_tags, handles_forex, atm_count,
                                    valid_from, valid_until)
        VALUES (OLD.id, OLD.name, OLD.address, OLD.lat, OLD.lng, OLD.coverage_radius_km,
                OLD.primary_industry_tags, OLD.handles_forex, OLD.atm_count,
                OLD.effective_from, next_effective);
        NEW.effective_from := next_effective;
        NEW.updated_at := now();
    ELSE
        -- 추적 대상 값이 그대로면 effective_from을 수동으로 바꾸지 못하게 고정한다.
        NEW.effective_from := OLD.effective_from;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
   SET search_path = cmaker, pg_temp;

DROP TRIGGER IF EXISTS trg_branch_effective_from ON branch;
CREATE TRIGGER trg_branch_effective_from
    BEFORE INSERT OR UPDATE ON branch
    FOR EACH ROW EXECUTE FUNCTION branch_apply_effective_from();

-- ---------------------------------------------------------------------
-- 3. app_user — 시스템 계정 (ERD의 USER, 운영자가 psql로 직접 INSERT)
--    password: 평문 저장 (docs/db-schema-decisions-review.md 결정 — 보안 검토 필요)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_user (
    id                      SERIAL PRIMARY KEY,
    branch_id               INT          REFERENCES branch(id),
    username                VARCHAR(50)  NOT NULL UNIQUE,
    name                    VARCHAR(50)  NOT NULL,
    role                    VARCHAR(20)  NOT NULL,
    password                VARCHAR(200) NOT NULL,
    session_timeout_minutes INT          NOT NULL DEFAULT 30,
    session_extendable      BOOLEAN      NOT NULL DEFAULT TRUE,
    is_active               BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT app_user_role_values CHECK (role IN ('RM', 'BRANCH_MANAGER', 'HQ_MARKETING', 'HQ_COMPLIANCE')),  -- VAL-08
    CONSTRAINT app_user_branch_by_role CHECK (                                                                   -- CONST-03
        (role IN ('HQ_MARKETING', 'HQ_COMPLIANCE') AND branch_id IS NULL)
        OR (role IN ('RM', 'BRANCH_MANAGER') AND branch_id IS NOT NULL)
    ),
    CONSTRAINT app_user_session_timeout_range CHECK (session_timeout_minutes BETWEEN 5 AND 480)
);

-- ---------------------------------------------------------------------
-- 4. data_source_snapshot — 외부 소스 원본 응답 (재현성, OPS-05 1년 보존)
--    (source_name, as_of_date) 인덱스가 날짜 파티션 조회 단위다.
--    동일 소스·기준일·원본(해시)은 한 번만 적재한다(재실행 시 동일 스냅샷 재사용).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_source_snapshot (
    id             SERIAL PRIMARY KEY,
    source_name    VARCHAR(40)  NOT NULL,
    as_of_date     DATE         NOT NULL,                  -- VAL-09
    fetched_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    request_params JSONB        NOT NULL DEFAULT '{}'::jsonb,
    payload_hash   CHAR(64)     NOT NULL,
    raw_payload    JSONB        NOT NULL,
    CONSTRAINT data_source_snapshot_unique UNIQUE (source_name, as_of_date, payload_hash)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_source_date ON data_source_snapshot(source_name, as_of_date DESC, id DESC);

-- ---------------------------------------------------------------------
-- 5. batch_run — 일간 배치 실행 이력 (REQ-17, UC-18)
--    ERD 순서상 14번이지만 signal/event/recommendation이 실행 ID를 참조하므로 먼저 만든다.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS batch_run (
    id              SERIAL PRIMARY KEY,
    run_type        VARCHAR(10) NOT NULL,
    status          VARCHAR(10) NOT NULL,
    triggered_by    INT         REFERENCES app_user(id),
    target_date     DATE        NOT NULL,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    failure_reason  TEXT,
    params_snapshot JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- 임계치·가중치·설정 버전(PRIN-08)
    stage_stats     JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- 단계별 처리 건수·소요시간(OPS-08)
    source_status   JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- 소스별 수집/폴백 결과(RULE-SENSE-04)
    CONSTRAINT batch_run_type_values CHECK (run_type IN ('SCHEDULED', 'MANUAL')),
    CONSTRAINT batch_run_status_values CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    CONSTRAINT batch_run_trigger_by_type CHECK (                                   -- CONST-16(단일 행 부분)
        (run_type = 'MANUAL' AND triggered_by IS NOT NULL)
        OR (run_type = 'SCHEDULED' AND triggered_by IS NULL)
    ),
    CONSTRAINT batch_run_failure_reason CHECK (status = 'FAILED' OR failure_reason IS NULL)
);
CREATE INDEX IF NOT EXISTS idx_batch_run_status ON batch_run(status);
CREATE INDEX IF NOT EXISTS idx_batch_run_requested ON batch_run(triggered_by, requested_at DESC);
-- CONST-17: RUNNING 실행은 동시에 최대 1건 (동시 요청 경쟁 조건까지 DB가 막는다)
CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_run_single_running ON batch_run (status) WHERE status = 'RUNNING';

-- ---------------------------------------------------------------------
-- 6. event — 임계치를 넘어 승격된 신호 (도메인 정의서 5.1절)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
    id               SERIAL PRIMARY KEY,
    branch_id        INT          NOT NULL REFERENCES branch(id),
    signal_type      VARCHAR(40)  NOT NULL,
    scope            VARCHAR(10)  NOT NULL,
    target_key       VARCHAR(80)  NOT NULL,        -- 동일 대상 판정 키 (예: BUSINESS:12, INDUSTRY:한식, AREA)
    promotion_reason TEXT         NOT NULL,
    occurred_on      DATE         NOT NULL,
    as_of_date       DATE         NOT NULL,        -- VAL-09 소스 기준일
    last_merged_on   DATE,                         -- 쿨다운 내 재발로 병합된 최근 일자(RULE-SENSE-01)
    score            NUMERIC(8,4) NOT NULL DEFAULT 0,  -- 상한 절사 순서(RULE-SENSE-02)
    status           VARCHAR(10)  NOT NULL,
    batch_run_id     INT          REFERENCES batch_run(id),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT event_scope_values CHECK (scope IN ('BUSINESS', 'INDUSTRY', 'AREA')),
    CONSTRAINT event_status_values CHECK (status IN ('ACTIVE', 'MERGED', 'TRIMMED'))
);
CREATE INDEX IF NOT EXISTS idx_event_branch_date ON event(branch_id, occurred_on);
CREATE INDEX IF NOT EXISTS idx_event_cooldown ON event(branch_id, signal_type, target_key, occurred_on DESC);

-- ---------------------------------------------------------------------
-- 7. business — 접촉 대상 사업체 (공개 데이터만, RULE-SEC-01)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business (
    id                SERIAL PRIMARY KEY,
    permit_mgt_no     VARCHAR(40)  UNIQUE,          -- 인허가 관리번호(CONST-13 병합키)
    sbiz_store_id     VARCHAR(40)  UNIQUE,          -- 소진공 상가업소번호(S-1 병합키)
    name              VARCHAR(200) NOT NULL,
    industry_code     VARCHAR(40)  NOT NULL DEFAULT '',
    industry_name     VARCHAR(100) NOT NULL DEFAULT '',
    address           VARCHAR(300),
    lat               NUMERIC(10,7) NOT NULL,       -- WGS84(VAL-11, CONST-14)
    lng               NUMERIC(10,7) NOT NULL,
    source_crs        VARCHAR(20)  NOT NULL,        -- 원본 좌표계(VAL-11, CONST-14)
    biz_reg_no        VARCHAR(10),                  -- VAL-04, NULL 허용
    operating_status  VARCHAR(10)  NOT NULL,
    status_source     VARCHAR(10)  NOT NULL,
    licensed_on       DATE,                         -- 신선도 항 ①(RULE-TARGET-05)
    status_checked_at DATE,
    population_as_of  DATE         NOT NULL,        -- 모집단 적재 기준(REQ-16)
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT business_merge_key CHECK (permit_mgt_no IS NOT NULL OR sbiz_store_id IS NOT NULL),
    CONSTRAINT business_biz_reg_no_format CHECK (biz_reg_no IS NULL OR biz_reg_no ~ '^[0-9]{10}$'),   -- VAL-04
    CONSTRAINT business_status_values CHECK (operating_status IN ('정상', '휴업', '폐업', '영업정지')),
    CONSTRAINT business_status_source_values CHECK (status_source IN ('PERMIT', 'SBIZ', 'NTS')),
    CONSTRAINT business_nts_requires_biz_no CHECK (biz_reg_no IS NOT NULL OR status_source <> 'NTS'),  -- CONST-15
    CONSTRAINT business_wgs84_range CHECK (lat BETWEEN 33 AND 39 AND lng BETWEEN 124 AND 132)          -- CONST-14
);
CREATE INDEX IF NOT EXISTS idx_business_status ON business(operating_status);
CREATE INDEX IF NOT EXISTS idx_business_lat_lng ON business(lat, lng);

-- ---------------------------------------------------------------------
-- 8. signal — 정규화된 신호 원장 (임계치 미달도 저장, RULE-SENSE-03)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signal (
    id           SERIAL PRIMARY KEY,
    snapshot_id  INT           NOT NULL REFERENCES data_source_snapshot(id),
    branch_id    INT           NOT NULL REFERENCES branch(id),
    business_id  INT           REFERENCES business(id),
    signal_type  VARCHAR(40)   NOT NULL,
    scope        VARCHAR(10)   NOT NULL,            -- 사유 계층(RULE-TARGET-06)
    target_key   VARCHAR(80)   NOT NULL,
    intensity    NUMERIC(4,3)  NOT NULL,            -- 0~1 정규화(스코어링 sᵢ)
    raw_value    NUMERIC(14,4) NOT NULL,            -- 임계치 비교값(THRESHOLD_CONFIG.unit 단위)
    unit         VARCHAR(10)   NOT NULL,
    detail       JSONB         NOT NULL DEFAULT '{}'::jsonb,  -- 브리프 사실 문장 근거값
    as_of_date   DATE          NOT NULL,            -- VAL-09
    event_id     INT           REFERENCES event(id),  -- NULL = 승격되지 않음
    batch_run_id INT           REFERENCES batch_run(id),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT signal_scope_values CHECK (scope IN ('BUSINESS', 'INDUSTRY', 'AREA')),
    CONSTRAINT signal_intensity_range CHECK (intensity BETWEEN 0 AND 1),
    CONSTRAINT signal_unique_per_snapshot UNIQUE (snapshot_id, branch_id, signal_type, target_key)
);
CREATE INDEX IF NOT EXISTS idx_signal_branch_date ON signal(branch_id, as_of_date);
CREATE INDEX IF NOT EXISTS idx_signal_event ON signal(event_id);

-- ---------------------------------------------------------------------
-- 9. recommendation — 접촉 명부 1건 (지점·일자별 TOP 20, 탐색 슬롯 3건 포함)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation (
    id                  SERIAL PRIMARY KEY,
    branch_id           INT          NOT NULL REFERENCES branch(id),
    business_id         INT          NOT NULL REFERENCES business(id),
    score               NUMERIC(8,4) NOT NULL,
    signal_score        NUMERIC(8,4) NOT NULL,      -- Σ wᵢ·sᵢ
    freshness_score     NUMERIC(4,3) NOT NULL,      -- R (RULE-TARGET-05)
    proximity           NUMERIC(4,3) NOT NULL,
    scale_fit           NUMERIC(4,3) NOT NULL,
    distance_km         NUMERIC(5,2) NOT NULL,
    reason_tier         VARCHAR(10)  NOT NULL,      -- RULE-TARGET-06
    rank_in_branch      INT          NOT NULL,
    is_exploration_slot BOOLEAN      NOT NULL DEFAULT FALSE,  -- 화면 비노출(RULE-TARGET-04)
    recommended_on      DATE         NOT NULL,
    batch_run_id        INT          REFERENCES batch_run(id),
    score_detail        JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- 신호별 기여·가중치(감사 추적)
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT recommendation_freshness_range CHECK (freshness_score BETWEEN 0 AND 1),
    CONSTRAINT recommendation_reason_tier_values CHECK (reason_tier IN ('BUSINESS', 'INDUSTRY', 'AREA')),
    CONSTRAINT recommendation_rank_range CHECK (rank_in_branch BETWEEN 1 AND 20),    -- CONST-06(단일 행 부분)
    CONSTRAINT recommendation_unique_business UNIQUE (branch_id, recommended_on, business_id),
    CONSTRAINT recommendation_unique_rank UNIQUE (branch_id, recommended_on, rank_in_branch)
);
CREATE INDEX IF NOT EXISTS idx_recommendation_branch_date ON recommendation(branch_id, recommended_on);
CREATE INDEX IF NOT EXISTS idx_recommendation_business ON recommendation(business_id, recommended_on DESC);

-- ---------------------------------------------------------------------
-- 10. recommendation_event — 추천의 선정 사유 이벤트 (N:M)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_event (
    recommendation_id INT NOT NULL REFERENCES recommendation(id) ON DELETE CASCADE,
    event_id          INT NOT NULL REFERENCES event(id),
    PRIMARY KEY (recommendation_id, event_id)
);

-- ---------------------------------------------------------------------
-- 11. brief — 상담 브리프 (RULE-BRIEF-01~03)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brief (
    id                SERIAL PRIMARY KEY,
    recommendation_id INT         NOT NULL UNIQUE REFERENCES recommendation(id) ON DELETE CASCADE,
    reason_summary    TEXT        NOT NULL,
    reason_facts      JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- [{text, sourceTag}]
    talk_script       TEXT        NOT NULL DEFAULT '',          -- 줄 단위, 최대 3문장
    checklist         TEXT        NOT NULL DEFAULT '',          -- 줄 단위
    citation_tags     JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- [[소스명, 기준일], ...]
    -- LLM: 게이트웨이 생성 화법 / TEMPLATE: LLM 미설정·장애 시 사실 문장만으로 만든 정형 화법 /
    -- REASON_ONLY: 검증(citation guard)에서 화법이 전부 차단되어 사유만 표시(RULE-BRIEF-02)
    generation_status VARCHAR(20) NOT NULL,
    validation_errors JSONB       NOT NULL DEFAULT '[]'::jsonb,
    prompt            TEXT,                                     -- CLAUDE.md §6 감사 추적
    model_version     VARCHAR(100),
    raw_output        TEXT,
    latency_ms        INT,
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT brief_generation_status_values CHECK (generation_status IN ('LLM', 'TEMPLATE', 'REASON_ONLY'))
);

-- ---------------------------------------------------------------------
-- 12. tag_feedback — 1클릭 태깅 (추천 1건당 최대 1건, 재태깅은 갱신)
--     추천이 삭제되더라도 태깅 이력은 유실되지 않도록 CASCADE를 걸지 않는다.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tag_feedback (
    id                SERIAL PRIMARY KEY,
    recommendation_id INT         NOT NULL UNIQUE REFERENCES recommendation(id),
    tagged_by         INT         NOT NULL REFERENCES app_user(id),
    tag_value         VARCHAR(10) NOT NULL,
    reject_reason     VARCHAR(20),
    tagged_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tag_feedback_value_values CHECK (tag_value IN ('VISITED', 'HOLD', 'REJECTED')),
    CONSTRAINT tag_feedback_reason_values CHECK (
        reject_reason IS NULL OR reject_reason IN ('ALREADY_CUSTOMER', 'NOT_TARGET', 'INFO_ERROR', 'UNREACHABLE')
    ),
    CONSTRAINT tag_feedback_reason_required CHECK ((tag_value = 'REJECTED') = (reject_reason IS NOT NULL))  -- VAL-06 / CONST-07
);
CREATE INDEX IF NOT EXISTS idx_tag_feedback_recommendation ON tag_feedback(recommendation_id);

-- ---------------------------------------------------------------------
-- 13. signal_weight — 신호×업종 학습 가중치 (MVP는 갱신 비활성, 초기값만 사용)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signal_weight (
    id            SERIAL PRIMARY KEY,
    signal_type   VARCHAR(40)   NOT NULL,
    industry_code VARCHAR(100)  NOT NULL DEFAULT '*',   -- '*' = 신호 전체(상위 계층, RULE-LEARN-03)
    weight        NUMERIC(4,3)  NOT NULL,
    base_weight   NUMERIC(4,3)  NOT NULL,               -- w₀ (룰 기반 초기 가중치)
    alpha         NUMERIC(12,4) NOT NULL DEFAULT 0,
    beta          NUMERIC(12,4) NOT NULL DEFAULT 0,
    sample_count  INT           NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT signal_weight_range CHECK (weight BETWEEN 0.2 AND 2.0),           -- VAL-10 / CONST-08
    CONSTRAINT signal_weight_base_range CHECK (base_weight BETWEEN 0.2 AND 2.0),
    CONSTRAINT signal_weight_unique UNIQUE (signal_type, industry_code)
);

-- ---------------------------------------------------------------------
-- 14. threshold_config — 신호 임계치·운영 파라미터 (REQ-14, UC-15)
--     category SIGNAL = 신호 승격 임계치, SYSTEM = 쿨다운·상한 등 운영 파라미터
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS threshold_config (
    id              SERIAL PRIMARY KEY,
    signal_type     VARCHAR(50)   NOT NULL UNIQUE,
    category        VARCHAR(10)   NOT NULL,
    label           VARCHAR(100)  NOT NULL,
    description     TEXT          NOT NULL DEFAULT '',
    threshold_value NUMERIC(12,4) NOT NULL,
    unit            VARCHAR(10)   NOT NULL,
    is_fixed        BOOLEAN       NOT NULL DEFAULT FALSE,  -- UI에서 변경 불가(예: 기상특보 발효 즉시)
    integer_only    BOOLEAN       NOT NULL DEFAULT FALSE,
    min_value       NUMERIC(12,4),
    max_value       NUMERIC(12,4),
    updated_by      INT           REFERENCES app_user(id),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT threshold_category_values CHECK (category IN ('SIGNAL', 'SYSTEM')),
    CONSTRAINT threshold_value_nonneg CHECK (threshold_value >= 0)              -- VAL-05
);

-- ---------------------------------------------------------------------
-- 15. audit_log — 감사 추적 로그 (REQ-15, 1년 이상 보존)
--     태깅 데이터는 신호 가중치 학습 외 용도(개인·지점 성과 평가)로 집계하지 않는다(CLAUDE.md §0.7).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGSERIAL PRIMARY KEY,
    actor_user_id INT         REFERENCES app_user(id),
    action        VARCHAR(40) NOT NULL,
    entity_type   VARCHAR(40) NOT NULL,
    entity_id     VARCHAR(40),
    before_value  JSONB,
    after_value   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id, created_at DESC);
