-- 2026-10-14 지점 이력 트리거: 효력 전 값은 이력에 남기지 않음 (함수 교체만, 데이터 변경 없음, 여러 번 실행해도 안전)
--
-- 실행: psql -U myapp_user -d myapp_db -v ON_ERROR_STOP=1 -f backend/database/patches/2026-10-14_branch_history_zero_interval.sql
--
-- 배경: branch_apply_effective_from()은 UPDATE 때 변경 전 값을 [OLD.effective_from, 다음 날 07:30) 구간으로
--       branch_history에 옮긴다. 지점을 등록한 당일 다시 고치거나(지오코딩 좌표 반영 포함) 같은 날 두 번 고치면
--       OLD.effective_from이 이미 '다음 날 07:30'이라 valid_from = valid_until인 0길이 구간이 생긴다.
--       10/14 데이터 검증에서 branch_history 11건이 전부 0길이였다.
--       0길이 구간은 load_effective_branches()의 조건(valid_from <= 기준 < valid_until)에 걸리지 않아
--       명부 계산에는 영향이 없지만, 한 번도 효력이 없던 값이 이력처럼 보인다.
--
-- 처리: 변경 전 값이 아직 효력 전(OLD.effective_from >= 다음 효력 시각)이면 이력 INSERT를 건너뛰도록 함수를 교체한다.
--       schema.sql의 같은 함수와 동일한 본문이다.
--       기존 0길이 이력 11건은 지점 개명·재사용 흔적(예: branch 1의 옛 이름 '강남중앙지점')이라 지우지 않는다.

BEGIN;
SET LOCAL search_path TO cmaker;

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
        IF OLD.effective_from < next_effective THEN
            INSERT INTO branch_history (branch_id, name, address, lat, lng, coverage_radius_km,
                                        primary_industry_tags, handles_forex, atm_count,
                                        valid_from, valid_until)
            VALUES (OLD.id, OLD.name, OLD.address, OLD.lat, OLD.lng, OLD.coverage_radius_km,
                    OLD.primary_industry_tags, OLD.handles_forex, OLD.atm_count,
                    OLD.effective_from, next_effective);
        END IF;
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

COMMIT;

-- 적용 확인(t가 정상)
SELECT position('OLD.effective_from < next_effective' IN p.prosrc) > 0 AS patched
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'cmaker' AND p.proname = 'branch_apply_effective_from';
