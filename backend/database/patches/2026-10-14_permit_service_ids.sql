-- 2026-10-14 약국·체력단련장업 개방서비스ID 확정 (테이블 구조 변경 없음, 여러 번 실행해도 안전)
--
-- 실행: psql -U myapp_user -d myapp_db -v ON_ERROR_STOP=1 -f backend/database/patches/2026-10-14_permit_service_ids.sql
--
-- 배경: 행안부 업종별 인허가 API(PERMIT_DAILY)는 응답에 구 개방서비스ID(opnSvcId)가 없어 pipeline.toml의
--       service_id를 관리번호 접두어로 붙인다(CONST-13 병합키 = "{service_id}-{관리번호}").
--       약국·체력단련장업은 ID를 몰라 경로명("pharmacies", "fitness_centers")을 임시로 쓰고 있었다.
--       확인값(서울 열린데이터광장 LOCALDATA_010106 = 약국, LOCALDATA_104201 = 체력단련장업):
--         약국          pharmacies      → 01_01_06_P
--         체력단련장업  fitness_centers → 10_42_01_P
--       월간 전수 CSV의 개방서비스아이디와 접두어가 같아져야 일간·월간 적재가 같은 사업체로 합쳐진다.
--
-- 처리: 임시 접두어로 적재된 BUSINESS 행의 permit_mgt_no·industry_code를 새 ID로 바꾼다.
--       같은 사업장이 이미 새 키로도 들어와 있으면(전수 CSV 선적재 등) 충돌을 피하려고 건드리지 않고 남겨 둔다.
--       남은 행 수는 마지막 SELECT로 확인한다(0이 정상).

BEGIN;
SET LOCAL search_path TO cmaker;

UPDATE business AS b
   SET permit_mgt_no = m.new_id || substr(b.permit_mgt_no, length(m.old_id) + 1),
       industry_code = m.new_id,
       updated_at    = now()
  FROM (VALUES ('pharmacies', '01_01_06_P'),
               ('fitness_centers', '10_42_01_P')) AS m(old_id, new_id)
 WHERE b.permit_mgt_no LIKE m.old_id || '-%'
   AND NOT EXISTS (
       SELECT 1 FROM business AS dup
        WHERE dup.permit_mgt_no = m.new_id || substr(b.permit_mgt_no, length(m.old_id) + 1)
   );

COMMIT;

-- 충돌로 남은 임시 접두어 행(0이 정상). 0이 아니면 같은 사업장이 두 행으로 존재한다.
SELECT split_part(permit_mgt_no, '-', 1) AS old_prefix, count(*) AS remaining
  FROM cmaker.business
 WHERE permit_mgt_no LIKE 'pharmacies-%' OR permit_mgt_no LIKE 'fitness_centers-%'
 GROUP BY 1;
