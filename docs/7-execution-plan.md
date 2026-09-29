# BranchSense 실행 계획

- **버전**: v1.4.0
- **작성일**: 2026-08-26 (최종 수정: 2026-09-08)

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.0.0 | 2026-08-26 | 초안 작성 |
| v1.0.1 | 2026-09-08 | 문서 정합성 점검 결과 반영: 참조 문서 버전 표기를 최신본에 맞게 정정 (내용 변경 없음) |
| v1.1.0 | 2026-09-08 | `2-prd.md` v1.2.0의 AWS Bedrock 결정 반영: SETUP-04, BATCH-04, Phase 2 상품 우선순위 작업 항목의 LLM/RAG 표현을 AWS Bedrock AI Agent/Knowledge Base로 갱신 |
| v1.2.0 | 2026-09-08 | `report/CHANGE-REQUEST_v1.md` 8단계 체크리스트 반영: POP 워크스트림 신설, 스프린트 1~2에 DATA-00(인허가 전수 커넥터)·POP-01(모집단 적재) 추가 — REQ-05의 선행 조건이므로 스프린트 3~4가 아닌 1~2로 배치. DATA-01/BATCH-01을 REQ-02 재정의(인허가 1차·국세청 2차)에 맞게, DATA-02~07/BATCH-02/BATCH-03을 인허가 변동분·신선도 항·사유 계층(RULE-TARGET-05/06)에 맞게 갱신. MVP 대상 REQ에 REQ-16 추가, M1 마일스톤에 모집단 적재 포함 |
| v1.3.0 | 2026-09-08 | 배치 지연/실패 대비 수동 재연동(REQ-17, UC-18) 반영: 스프린트 6에 API-06(수동 재실행 API)·FE-07(수동 재연동 버튼) 추가, MVP 대상 REQ에 REQ-17 추가 |
| v1.4.0 | 2026-09-08 | `report/db-schema-decisions-review.md` 검토 결과 반영: 스프린트 1~2에서 API-01(지점 등록·수정 API)·FE-01(지점 등록 화면)을 제거(UC-01·UC-02·API-01 MVP 스코프 제외, 운영자 psql 직접 입력으로 대체), SETUP-01 완료 기준에서 지오코딩 관련 문구 제거. 신규 GEO-01(좌표 지오코딩 배치, RULE-BRANCH-03) 작업 추가. INFRA-03 완료 기준에서 "UC-01 완료" 표현을 "지점 데이터 psql 적재 완료"로 정정 |

---

## 0. 문서 목적 및 전제

본 문서는 `2-prd.md`(v1.4.0) 8장의 단계별 일정(MVP/Phase 2/Phase 3)을 실행 가능한 작업 항목 단위로 분해한다. 각 작업은 `1-domain-definition.md`의 REQ/UC, `4-project-principle.md`의 디렉토리 구조와 연결되어 있어, 완료 여부를 코드 위치와 인수 기준으로 검증할 수 있다.

MVP는 2주 스프린트 6회(12주)로 운영하고, Phase 2·3는 스프린트 단위 대신 워크스트림 단위로 계획한다(원거리 일정은 세부 스프린트보다 범위 고정이 더 중요하기 때문).

---

## 1. 작업 항목 분류 체계

| 접두어 | 워크스트림 | 대응 디렉토리(`4-project-principle.md` 6장) |
|---|---|---|
| SETUP | 프로젝트 초기 셋업 | 저장소 루트, `backend/`, `frontend/` 스캐폴딩 |
| DATA | 소스 커넥터 구현 | `backend/batch/connectors/` |
| POP | 사업체 모집단 적재 | `backend/batch/population/`, `common/geo.py` |
| BATCH | 판정·채점·생성·학습 파이프라인 | `backend/batch/{normalizers,sensing,targeting,briefing,learning}/` |
| API | API 서버 구현 | `backend/api/` |
| FE | 프론트엔드 화면 구현 | `frontend/src/` |
| INFRA | 배포·모니터링·보안 | 저장소 루트 인프라 설정, CI |

---

## 2. MVP 실행 계획 (0~3개월)

대상 REQ: REQ-01, 02, 03, 05, 06, 07, 08, 14, 15, 16, 17 (`2-prd.md` 3장 필수 항목)

### 스프린트 0 (1주) — 셋업

| ID | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| SETUP-01 | 저장소 구조 생성, `database/schema.sql` 초기 스키마(BRANCH·BRANCH_HISTORY·USER·DATA_SOURCE_SNAPSHOT), BRANCH INSERT/UPDATE 이력 트리거(CONST-19) | REQ-01 | `4-project-principle.md` 6장 트리와 일치, psql로 스키마 적용 성공, 지점 정보 UPDATE 시 옛 값이 BRANCH_HISTORY에 쌓이고 effective_from이 익일로 갱신됨을 확인 |
| SETUP-02 | FastAPI 앱 골격 + 인증 미들웨어 | REQ-01 | 로그인 후 JWT 발급, 보호된 엔드포인트 401 처리 확인 |
| SETUP-03 | React 앱 골격 + 라우터 + 디자인 토큰 초기화 | — | `9-style-guide.md` 2~4장 토큰이 `:root`에 반영됨 |
| SETUP-04 | AWS Bedrock 클라이언트 설정(IAM 자격증명, Agent ID, Knowledge Base ID) | `2-prd.md` v1.2.0 5장/10장 미해결 이슈 2 | Bedrock 연동 정보가 `common/config.py`에 반영되고 테스트 호출(Agent invoke) 성공 |

### 스프린트 1~2 (2주) — 지점 좌표 지오코딩, 모집단 적재, 사업자 검증

> ⚠️ `report/CHANGE-REQUEST_v1.md` 반영: POP-01(모집단 적재)은 REQ-05(스코어링)의 선행 조건이라 뒤로 미룰 수 없으므로 이 스프린트로 당겼다. 착수 전 `2-prd.md` 10장 미해결 이슈 7번(data.go.kr 실제 제공 스펙)을 먼저 확인한다.

| ID | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| GEO-01 | 좌표 지오코딩 배치(`geocoding/geocode_job.py`, 10분 주기) | REQ-01, RULE-BRANCH-03 | lat/lng가 NULL이거나 주소가 바뀐 BRANCH를 대상으로 좌표를 채움, 재시도·알림 로직 없음을 확인(`report/db-schema-decisions-review.md`) |
| DATA-00 | 지방행정 인허가 전수 커넥터(`permit_connector.fetch_all_businesses`) | REQ-16 | data.go.kr에서 담당 지자체·업종 범위 전수 자료 취득 확인 |
| POP-01 | `common/geo.py`(EPSG:5174→WGS84) + 모집단 적재 배치(`population/business_loader.py`, `run_monthly.py`) | REQ-16, UC-17 | UC-17 인수 기준 5항목 전부 통과, VAL-11 좌표 변환 검증 |
| DATA-01 | 국세청 사업자등록상태 커넥터 (보완 검증용) | REQ-02 | 사업자번호 확보 건에 한해 호출, 호출 한도(1회 100건, 1일 100만건) 준수, 상태값이 인허가 값을 덮어씀(RULE-TARGET-01) |
| BATCH-01 | 사업자 상태 검증 배치(`run_daily.py` 1단계) — 인허가 영업상태 1차, 국세청 보완 2차 | REQ-02, UC-03 | UC-03 인수 기준 4항목(v1.1 갱신) 전부 통과 |

### 스프린트 3~4 (2주) — 일간 신호와 접촉 명부

| ID | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| DATA-02~07 | 인허가 변동분(`permit_connector.fetch_daily_changes`)·지하철·ECOS·오피넷·기상청·재난문자 커넥터 6종 | REQ-03 | 소스별 스냅샷 적재 확인, 장애 주입 시 RULE-SENSE-04 폴백 동작 |
| BATCH-02 | 신호 정규화(사유 범위 `scope` 태깅 포함) + 이벤트 승격(sensing) | REQ-03 | 도메인 정의서 5.1절 판정 순서 단위 테스트(TEST-01) 통과 |
| BATCH-03 | 배제·스코어링(신선도 항 R)·사유 계층·탐색 슬롯(targeting) | REQ-05 | RULE-TARGET-01~06 단위 테스트(TEST-02) 통과. POP-01이 적재한 BUSINESS를 전제로 함(선행 조건) |
| BATCH-04 | AWS Bedrock AI Agent 브리프 생성 + citation guard | REQ-06 | RULE-BRIEF-01~03 회귀 테스트셋(TEST-03) 통과 |
| API-02 | 추천/브리프 조회 API | REQ-05, REQ-06, UC-06, UC-07 | UC-06, UC-07 인수 기준 통과 |
| FE-02 | 오늘의 접촉 TOP 20 대시보드 | UC-06 | 07:35 접속 시 목록·사유 노출 확인(SC-02) |
| FE-03 | 상담 브리프 상세 화면 | UC-07 | 출처 태그 전 항목 노출 확인 |

### 스프린트 5 (2주) — 태깅·CRM·관리자 설정

| ID | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| API-03 | 태깅 저장 API | REQ-08, UC-09 | VAL-06, 클릭 1회 저장 확인 |
| FE-04 | 태깅 버튼 컴포넌트 + 미태깅 상기 배너 | UC-09 | SC-03 정상/예외 흐름 통과 |
| API-04 | CRM 등록 파일 생성 API | REQ-07, UC-08 | 다운로드 파일이 CRM 컬럼 매핑과 일치(`[CRM팀 확인 필요]` 스펙 확정 후) |
| FE-05 | CRM 파일 다운로드 버튼 | UC-08 | 수작업 편집 없이 등록 가능함을 CRM팀과 교차 확인 |
| API-05 | 임계치 관리자 설정 API | REQ-14, UC-15 | VAL-05, 변경 이력 저장 확인 |
| FE-06 | 임계치 관리 화면(본부용) | UC-15 | SC-04 정상/예외 흐름 통과 |
| INFRA-01 | 감사 추적 로그 저장 구조 | REQ-15 | 추천·브리프·태깅·임계치 변경 이력이 1년 보존 정책으로 저장됨 |

### 스프린트 6 (2주) — 파일럿 준비 및 안정화

| ID | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| INFRA-02 | 07:30 SLA 모니터링 및 배치 실패 알림 | `2-prd.md` 6장 | 4주 연속 SLA 충족 측정 시작 |
| API-06 | 배치 수동 재실행 API(`batch.router.py`/`batch.service.py`) — 권한 검증, 중복 실행 방지, 쿨다운 | REQ-17, UC-18 | RULE-SENSE-06·VAL-12 단위 테스트 통과, `BATCH_RUN` 기록 확인 |
| FE-07 | 수동 재연동 버튼(`ManualBatchTrigger`) + 상태 폴링(`useBatchRunStatus`) | REQ-17, UC-18 | UC-18 인수 기준 6항목 전부 통과(SC-09) |
| INFRA-03 | 파일럿 지점 온보딩(데이터 이관, 계정 발급) | `2-prd.md` 10장 미해결 이슈 3 | 파일럿 지점 전원 운영자 psql 직접 입력으로 BRANCH·USER 적재 완료(UC-01·UC-02 MVP 스코프 제외) |
| TEST-01 | 재현성 회귀 테스트(TEST-06) 1차 실행 | PRIN-08 | 동일 스냅샷 재실행 시 동일 산출물 확인 |

**MVP 종료 조건**(`2-prd.md` 8장): 태깅률 70%, 명부 내 휴폐업 포함 0건, 07:30 SLA 4주 연속 충족.

---

## 3. Phase 2 실행 계획 (4~6개월)

대상 REQ: REQ-04, 09, 10, 11

| 워크스트림 | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| DATA | 소진공 상가(상권)정보 커넥터, 분기 갱신 감지 로직 | REQ-04, UC-05 | RULE-SENSE-05(갱신일에만 실행) 검증 |
| BATCH | 채택률 집계 + 가중치 갱신 배치(learning) | REQ-09, UC-10 | RULE-LEARN-01~05, 도메인 정의서 5.2절 계산 단위 테스트 통과 |
| BATCH | 운영 수요 예측(현금/ATM/외화) 로직 | REQ-10 | 예측 구간 산출, 근거 신호 태깅 |
| BATCH | 상품 우선순위 + AWS Bedrock Knowledge Base 인용 | REQ-11 | 인용 없는 항목 비노출 검증 |
| API/FE | 채택률 대시보드, 운영 브리핑 화면 | UC-11, UC-16 | SC-05, SC-06 흐름 통과 |
| INFRA | 탐색 슬롯 성과 분리 집계 파이프라인 | RULE-LEARN-04 | 탐색 슬롯 태깅 결과가 별도 지표로 조회 가능 |

**Phase 2 종료 조건**: MVP 베이스라인 대비 채택률 상대 +20%, 운영 예측 구간 적중률 80%.

---

## 4. Phase 3 실행 계획 (7~12개월)

대상 REQ: REQ-12, 13

| 워크스트림 | 작업 | 관련 REQ/UC | 완료 기준 |
|---|---|---|---|
| BATCH | 캠페인 트리거 판정(재난문자·연속 특보) | REQ-12 | 트리거 조건 단위 테스트 |
| BATCH | 캠페인 초안 생성(문자/게시물) | REQ-12 | VAL-07(광고성 표기·수신거부) 검증 |
| API/FE | 캠페인 검토·승인 흐름, 상황판 | UC-12~14 | SC-07 정상/예외 흐름 통과, RULE-CAMPAIGN-01 우회 경로 없음 확인 |
| INFRA | 전행 확산 롤아웃, CRM 연동 고도화 | `2-prd.md` 10장 미해결 이슈 4 | 전 지점 온보딩 완료 |

**Phase 3 종료 조건**: 준법 승인 흐름 무결성 검증, 전행 롤아웃 완료.

---

## 5. 마일스톤 및 게이트 기준

| 마일스톤 | 시점 | 게이트 기준 | 실패 시 조치 |
|---|---|---|---|
| M1 | 스프린트 2 종료 | 지점 등록·**사업체 모집단 적재(POP-01)**·사업자 검증 완료, 파일럿 지점 데이터 확보 | 데이터 확보 지연 시 스프린트 3 착수를 보류 |
| M2 | 스프린트 4 종료 | 일간 신호 배치 07:30 SLA 1주 시범 충족 | 미충족 시 소스 수 축소 후 재시도 |
| M3 (MVP 종료) | 스프린트 6 종료 | `2-prd.md` 8장 MVP 종료 조건 3개 항목 전부 충족 | 미충족 항목만 스프린트 연장, 나머지는 Phase 2 착수 |
| M4 (Phase 2 종료) | 6개월 시점 | 채택률 상대 +20%, 예측 적중률 80% | 가중치 학습 로직 재검토 |
| M5 (Phase 3 종료) | 12개월 시점 | 준법 무결성 검증, 전행 롤아웃 | 준법 이슈 발견 시 롤아웃 중단 후 재승인 절차 재설계 |

---

## 6. 참고 문서

- `1-domain-definition.md` (v1.4.0): REQ, UC, RULE, 핵심 계산값 정의
- `2-prd.md` (v1.4.0): 3장 범위 우선순위, 5장 기술 스택(AWS Bedrock), 8장 일정, 9장 리스크, 10장 미해결 이슈
- `report/db-schema-decisions-review.md`: 지점 등록·수정 API/화면 제외, 지오코딩 배치 분리 결정 근거
- `3-user-scenario.md` (v1.2.0): SC-01~09 (완료 기준의 시나리오 근거)
- `4-project-principle.md` (v1.5.0): 6장 디렉토리 구조 (작업 항목의 코드 위치 근거)
- `report/CHANGE-REQUEST_v1.md`: POP 워크스트림·스프린트 재배치 근거
