# DB 테이블 정리

- **DB**: PostgreSQL 17
- **ORM**: 미사용 (직접 SQL, psycopg)
- **스키마 파일**: `database/schema.sql` 단일 파일 관리
- **참고 문서**: `6-erd.md` (v1.0.0)

---

## 테이블 목록

| 테이블 | 설명 | 단계 |
|--------|------|------|
| [BRANCH](#branch) | 영업점 | MVP |
| [USER](#user) | 시스템 계정 | MVP |
| [DATA_SOURCE_SNAPSHOT](#data_source_snapshot) | 외부 소스 원본 응답 적재본 | MVP |
| [SIGNAL](#signal) | 정규화된 신호 레코드 | MVP |
| [EVENT](#event) | 임계치 초과로 승격된 신호 | MVP |
| [BUSINESS](#business) | 접촉 대상 사업체 | MVP |
| [RECOMMENDATION](#recommendation) | 접촉 명부 1건 | MVP |
| [RECOMMENDATION_EVENT](#recommendation_event) | 추천-이벤트 연결 (N:M) | MVP |
| [BRIEF](#brief) | 추천에 대한 생성 콘텐츠 | MVP |
| [TAG_FEEDBACK](#tag_feedback) | 담당자 1클릭 태깅 | MVP |
| [SIGNAL_WEIGHT](#signal_weight) | 신호×업종 학습 가중치 | Phase 2 |
| [THRESHOLD_CONFIG](#threshold_config) | 신호별 임계치 설정 | MVP |
| [OPERATION_FORECAST](#operation_forecast) | 영업점 운영 수요 예측 | Phase 2 |
| [CAMPAIGN](#campaign) | 캠페인 | Phase 3 |
| [CAMPAIGN_TARGET_BRANCH](#campaign_target_branch) | 캠페인-지점 연결 (N:M) | Phase 3 |
| [CAMPAIGN_DRAFT](#campaign_draft) | 캠페인 초안 | Phase 3 |
| [APPROVAL_LOG](#approval_log) | 캠페인 승인 이력 | Phase 3 |

---

## BRANCH

영업점 기본 정보. 신호 감지·스코어링의 공간 기준점이 되는 테이블.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| branch_code | VARCHAR(20) | UNIQUE, NOT NULL | 영문 대문자+숫자 조합 (VAL-01) |
| name | VARCHAR | NOT NULL | 지점명 |
| address | VARCHAR | NOT NULL | 도로명 주소 |
| lat | DECIMAL | NOT NULL | 위도 (지오코딩 필수, VAL-03) |
| lng | DECIMAL | NOT NULL | 경도 (지오코딩 필수, VAL-03) |
| coverage_radius_km | DECIMAL(3,1) | NOT NULL | 담당 상권 반경, 0.5~3.0 (VAL-02) |
| primary_industry_tags | VARCHAR | | 주력 업종 태그 |
| handles_forex | BOOLEAN | NOT NULL | 외화 취급 여부 |
| atm_count | INT | NOT NULL | ATM 대수 |
| effective_from | TIMESTAMP | NOT NULL | 변경 반영 시작 시각 (RULE-BRANCH-01: 변경 익일 배치부터 반영) |

**주요 제약**
- `branch_code` 중복 등록 불가. 기존 레코드 수정으로 처리 (RULE-BRANCH-02)
- 지오코딩 실패 시 저장 불가 (VAL-03)
- 정보 변경은 저장 즉시가 아닌 **다음 날 07:30 배치부터** 반영 (RULE-BRANCH-01)

---

## USER

시스템 계정. RM, 지점장, 본부 역할로 구분.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| branch_id | INT | FK → BRANCH.id, NULL 허용 | 본부(HQ) 역할은 NULL (VAL-08) |
| name | VARCHAR | NOT NULL | |
| role | VARCHAR(20) | NOT NULL | 'RM' / 'BRANCH_MANAGER' / 'HQ' (VAL-08) |
| password_hash | VARCHAR | NOT NULL | |

**주요 제약**
- `role = 'HQ'`이면 `branch_id`는 반드시 NULL
- `role = 'RM'` 또는 `'BRANCH_MANAGER'`이면 `branch_id` 필수

---

## DATA_SOURCE_SNAPSHOT

공공 데이터 소스의 원본 응답을 날짜 파티션으로 적재. 재현성 보장 목적.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| source_name | VARCHAR | NOT NULL | 소스명 (예: 국세청, 기상청) |
| as_of_date | DATE | NOT NULL | 데이터 기준일 (VAL-09, NULL 불가) |
| fetched_at | TIMESTAMP | NOT NULL | 실제 수집 시각 |
| raw_payload | JSONB | NOT NULL | 원본 응답 전문 |

**용도**: 외부 소스 장애 시 전일 스냅샷으로 폴백 (RULE-SENSE-04), 과거 추천 재현 검증

---

## SIGNAL

외부 데이터에서 정규화된 신호 레코드. 임계치 미달 신호도 여기에 저장.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| snapshot_id | INT | FK → DATA_SOURCE_SNAPSHOT.id | 원본 스냅샷 참조 |
| branch_id | INT | FK → BRANCH.id | 신호 대상 지점 |
| business_id | INT | FK → BUSINESS.id, NULL 허용 | 사업체 단위 신호가 아니면 NULL |
| signal_type | VARCHAR | NOT NULL | '사업자' / '상권' / '거시환경' |
| intensity | DECIMAL(4,3) | NOT NULL | 신호 강도, 0.000~1.000 정규화값 |
| as_of_date | DATE | NOT NULL | 신호 기준일 (VAL-09) |
| event_id | INT | FK → EVENT.id, NULL 허용 | 임계치 초과 시 EVENT 참조, 미달 시 NULL (RULE-SENSE-03) |

**주요 제약**
- `event_id`가 NULL이 아니려면 해당 신호의 `intensity`가 임계치를 초과해야 함 (RULE-SENSE-03)
- 임계치 미달 신호도 SIGNAL 원장에는 저장됨 (이벤트 승격만 안 될 뿐)

---

## EVENT

임계치를 초과해 실무 처리 대상으로 승격된 신호.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| branch_id | INT | FK → BRANCH.id | 발생 지점 |
| promotion_reason | VARCHAR | NOT NULL | 승격 사유 |
| occurred_on | DATE | NOT NULL | 발생일 |
| status | VARCHAR(10) | NOT NULL | 'ACTIVE' / 'MERGED' / 'TRIMMED' |

**status 설명**
| 값 | 설명 | 규칙 |
|----|------|------|
| ACTIVE | 활성 이벤트 | |
| MERGED | 쿨다운(14일) 내 동일 신호 재발로 기존 이벤트에 병합됨 | RULE-SENSE-01 |
| TRIMMED | 지점 일일 상한(8건) 초과로 점수 하위 항목 절사 | RULE-SENSE-02 |

**주요 제약**
- 지점별 하루 ACTIVE 이벤트 상한 8건 (RULE-SENSE-02)
- 쿨다운(14일) 내 동일 대상·동일 신호종류 재발 시 신규 생성 안 하고 기존에 병합 (RULE-SENSE-01)

---

## BUSINESS

접촉 대상 사업체. 공개 데이터(사업자등록·인허가·상가정보)만으로 구성. 개인 고객정보 없음.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| name | VARCHAR | NOT NULL | 상호명 |
| industry_code | VARCHAR | NOT NULL | 업종 코드 |
| lat | DECIMAL | | 위도 |
| lng | DECIMAL | | 경도 |
| biz_reg_no | VARCHAR(10) | NOT NULL | 사업자번호 10자리 숫자 (VAL-04) |
| operating_status | VARCHAR(10) | NOT NULL | '정상' / '휴업' / '폐업' / '영업정지' |
| status_checked_at | DATE | NOT NULL | 상태 최근 확인일 |

**주요 제약**
- `operating_status`는 UC-03 배치(국세청 API)가 갱신
- 휴업/폐업/영업정지 상태는 배제 필터 1순위 (RULE-TARGET-01)
- 개인 고객정보·거래정보 포함 금지 (RULE-SEC-01)

---

## RECOMMENDATION

지점별 접촉 명부 1건. 매일 배치가 TOP 20 + 탐색 슬롯 3건 생성.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| branch_id | INT | FK → BRANCH.id | 소속 지점 |
| business_id | INT | FK → BUSINESS.id | 추천 대상 사업체 |
| score | DECIMAL | NOT NULL | 스코어링 점수 |
| rank_in_branch | INT | NOT NULL | 지점 내 순위 1~20 |
| is_exploration_slot | BOOLEAN | NOT NULL | 탐색 슬롯 여부 (RULE-TARGET-03/04) |
| recommended_on | DATE | NOT NULL | 추천 생성일 |

**주요 제약**
- 지점·일자 기준 `rank_in_branch`는 1~20 범위
- `is_exploration_slot = TRUE`인 행은 정확히 3건 (RULE-TARGET-03)
- 탐색 슬롯 여부는 담당자 화면에 노출 안 함 (RULE-TARGET-04)
- 스코어 공식: `Score = (Σ wᵢ·sᵢ) × 근접도 × 규모적합도` (RULE-TARGET-02)

---

## RECOMMENDATION_EVENT

추천과 이벤트의 N:M 연결 테이블. 추천 1건의 선정 사유는 여러 이벤트를 근거로 가질 수 있음.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| recommendation_id | INT | FK → RECOMMENDATION.id, PK | |
| event_id | INT | FK → EVENT.id, PK | |

---

## BRIEF

추천 1건에 대한 LLM 생성 콘텐츠. 브리프는 추천당 최대 1건.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| recommendation_id | INT | FK → RECOMMENDATION.id, UNIQUE | |
| reason_summary | TEXT | NOT NULL | 선정 사유 1줄 요약 |
| talk_script | TEXT | NOT NULL | 화법 |
| checklist | TEXT | NOT NULL | 체크리스트 |
| citation_tags | JSONB | NOT NULL | 출처 태그 배열 `[소스명, 기준일]` (RULE-BRIEF-01) |

**주요 제약**
- 모든 사실 문장에 출처 태그 필수 (RULE-BRIEF-01)
- 도구 조회 결과에 근거 없는 문장은 생성 단계에서 차단 (RULE-BRIEF-02)
- 확정 수익·원금 보장 등 금칙 표현 필터링 (RULE-BRIEF-03)

---

## TAG_FEEDBACK

RM의 1클릭 태깅. 추천당 최대 1건(재태깅 시 갱신).

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| recommendation_id | INT | FK → RECOMMENDATION.id, UNIQUE | |
| tagged_by | INT | FK → USER.id | 태깅한 RM |
| tag_value | VARCHAR(10) | NOT NULL | 'VISITED' / 'HOLD' / 'REJECTED' |
| reject_reason | VARCHAR(20) | NULL 허용 | 'REJECTED'일 때만 필수 (VAL-06) |
| tagged_at | TIMESTAMP | NOT NULL | |

**tag_value 설명**
| 값 | 의미 | 채택률 계산 |
|----|------|-------------|
| VISITED | 방문함 | 분자·분모 모두 포함 |
| HOLD | 보류 | 분모에만 포함 (RULE-LEARN-02) |
| REJECTED | 부적합 | 분모에만 포함 |

**주요 제약**
- `tag_value = 'REJECTED'`이면 `reject_reason` 필수 (VAL-06)
- 미태깅 추천은 채택률 분모 제외, 태깅률 별도 관리 (RULE-LEARN-01)

---

## SIGNAL_WEIGHT

신호×업종 단위 학습 가중치. 전역 파라미터 (지점에 속하지 않음).

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| signal_type | VARCHAR | NOT NULL | 신호 종류 |
| industry_code | VARCHAR | NOT NULL | 업종 코드 |
| weight | DECIMAL(4,3) | NOT NULL | 가중치 0.2~2.0 (VAL-10) |
| alpha | DECIMAL | NOT NULL | 베타분포 파라미터 α |
| beta | DECIMAL | NOT NULL | 베타분포 파라미터 β |
| sample_count | INT | NOT NULL | 누적 표본 수 |
| updated_at | TIMESTAMP | NOT NULL | 최근 갱신 시각 |

**주요 제약**
- `weight`는 0.2~2.0으로 클리핑 (VAL-10)
- `sample_count < 30`이면 갱신 배치 대상 제외, 상위 계층 가중치 상속 (RULE-LEARN-03)
- 가중치 갱신 주 1회 배치로만 수행 (RULE-LEARN-05)

---

## THRESHOLD_CONFIG

본부가 UI에서 조정하는 신호별 임계치 설정.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| signal_type | VARCHAR | NOT NULL | 신호 종류 |
| threshold_value | DECIMAL | NOT NULL | 임계치 값, 0 이상 (VAL-05) |
| unit | VARCHAR | NOT NULL | 단위 (%, 건, ℃ 등) |
| updated_by | INT | FK → USER.id | 최근 수정 계정 |
| updated_at | TIMESTAMP | NOT NULL | 최근 수정 시각 |

**주요 제약**
- 변경 즉시 저장, 다음 배치부터 적용
- 변경 이력(수정 계정·일시·이전값)은 REQ-15 감사 로그로 보존

---

## OPERATION_FORECAST

지점 운영 수요 예측 결과. (Phase 2)

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| branch_id | INT | FK → BRANCH.id | 대상 지점 |
| forecast_type | VARCHAR | NOT NULL | '현금' / 'ATM' / '외화' |
| range_low | DECIMAL | NOT NULL | 예측 구간 하한 |
| range_high | DECIMAL | NOT NULL | 예측 구간 상한 |
| basis_signal_ids | JSONB | NOT NULL | 근거 신호 ID 배열 |
| as_of_date | DATE | NOT NULL | 예측 기준일 |

---

## CAMPAIGN

공익 이벤트 기반 캠페인. (Phase 3)

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| trigger_event_id | INT | FK → EVENT.id, NULL 허용 | 트리거 이벤트 |
| status | VARCHAR(20) | NOT NULL | 'DRAFT' / 'MANAGER_REVIEW' / 'APPROVED' / 'HANDED_OFF' |
| created_at | TIMESTAMP | NOT NULL | |

**status 전이 순서**
```
DRAFT → MANAGER_REVIEW → APPROVED → HANDED_OFF
```
- `HANDED_OFF`가 되려면 APPROVAL_LOG에 MANAGER + COMPLIANCE 승인이 모두 필요 (RULE-CAMPAIGN-01)

---

## CAMPAIGN_TARGET_BRANCH

캠페인과 대상 지점의 N:M 연결 테이블. (Phase 3)

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| campaign_id | INT | FK → CAMPAIGN.id, PK | |
| branch_id | INT | FK → BRANCH.id, PK | |

---

## CAMPAIGN_DRAFT

캠페인 문구 초안. 검토 과정에서 버전이 쌓임. (Phase 3)

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| campaign_id | INT | FK → CAMPAIGN.id | |
| message_body | TEXT | NOT NULL | 캠페인 문구 본문 |
| has_ad_disclosure | BOOLEAN | NOT NULL | 광고성 정보 표기 포함 여부 (VAL-07) |
| version | INT | NOT NULL | 초안 버전 번호 |

**주요 제약**
- `has_ad_disclosure = FALSE`이면 지점장 검토 요청(MANAGER_REVIEW 전이) 불가 (VAL-07)
- 광고성 정보 표기·수신거부 문구 자동 포함 (RULE-CAMPAIGN-02)

---

## APPROVAL_LOG

캠페인 승인 이력. (Phase 3)

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | SERIAL | PK | |
| campaign_id | INT | FK → CAMPAIGN.id | |
| stage | VARCHAR | NOT NULL | 'MANAGER' / 'COMPLIANCE' |
| approved_by | INT | FK → USER.id | 승인자 계정 |
| approved_at | TIMESTAMP | NOT NULL | 승인 시각 |

---

## 테이블 간 관계 요약

```
BRANCH ──< USER
BRANCH ──< EVENT ──< RECOMMENDATION_EVENT >── RECOMMENDATION
BRANCH ──< RECOMMENDATION ──< BRIEF
                           ──< TAG_FEEDBACK
                           ──< RECOMMENDATION_EVENT
BUSINESS ──< RECOMMENDATION
DATA_SOURCE_SNAPSHOT ──< SIGNAL >── EVENT
SIGNAL_WEIGHT (전역, 지점 무관)
THRESHOLD_CONFIG
EVENT ──o CAMPAIGN ──< CAMPAIGN_DRAFT
                   ──< APPROVAL_LOG
                   ──< CAMPAIGN_TARGET_BRANCH >── BRANCH
OPERATION_FORECAST >── BRANCH
```

---

## 단계별 구현 순서

| 단계 | 생성할 테이블 |
|------|--------------|
| MVP | BRANCH, USER, DATA_SOURCE_SNAPSHOT, SIGNAL, EVENT, BUSINESS, RECOMMENDATION, RECOMMENDATION_EVENT, BRIEF, TAG_FEEDBACK, THRESHOLD_CONFIG |
| Phase 2 | SIGNAL_WEIGHT, OPERATION_FORECAST |
| Phase 3 | CAMPAIGN, CAMPAIGN_TARGET_BRANCH, CAMPAIGN_DRAFT, APPROVAL_LOG |
