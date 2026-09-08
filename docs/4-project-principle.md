# BranchSense 프로젝트 구조 설계 원칙

- **버전**: v1.3.0
- **작성일**: 2026-08-26 (최종 수정: 2026-09-08)

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.0.0 | 2026-08-26 | 초안 작성 |
| v1.1.0 | 2026-09-08 | 6장 프론트엔드 디렉토리 구조에 공통 컴포넌트 3개(`TopUtilityBar`, `Tabs`, `ToggleSwitch`) 추가 — `8-wireframe.md`·`9-style-guide.md` v1.1.0에서 정의한 상단 유틸리티 바·상태 필터 탭·표시 개인화 토글에 대응 |
| v1.1.1 | 2026-09-08 | 문서 정합성 점검 결과 반영: OPS-03에 본부 하위 역할(마케팅/준법) 기반 접근 제어 명시. 하위 문서 인용 버전 정정 |
| v1.1.2 | 2026-09-08 | 큰글 모드(표시 개인화) 기능 제외 결정에 따라 6장 디렉토리 구조에서 `ToggleSwitch.tsx`를 제거 |
| v1.2.0 | 2026-09-08 | `2-prd.md` v1.2.0의 AWS Bedrock 결정 반영: "판단은 코드, 문장은 LLM" 전제를 Bedrock AI Agent 기준으로 갱신, `llm_client.py`를 `bedrock_agent_client.py`로 개명, OPS-01(환경변수 관리 → IAM 자격증명)·OPS-06(LLM 호출 격리 → 생성형 AI 호출 격리) 갱신 |
| v1.3.0 | 2026-09-08 | `report/CHANGE-REQUEST_v1.md` CHG-07 반영: `localdata_connector`를 `permit_connector`로 개명하고 전수/변동분 함수 분리(NAME-B03), 6장 백엔드 디렉토리에 `population/`(모집단 적재)·`run_monthly.py`·`common/geo.py`·`common/schemas/business.py`·`targeting/reason_tier.py` 추가, `population`이 일간 SLA 파이프라인과 분리된 별도 진입점임을 §2에 명시 |

---

## 0. 문서 목적 및 전제

본 문서는 `1-domain-definition.md`(v1.2.0), `2-prd.md`(v1.2.0), `3-user-scenario.md`(v1.1.0)에 정의된 요구사항을 실제 코드로 구현할 때 따라야 할 프로젝트 구조·코드 설계 원칙을 정의한다.

전제 조건은 다음과 같으며, 아래 모든 원칙은 이 전제를 최우선으로 따른다.

- **배치와 API는 별도 실행 단위**다. 배치(신호 감지·스코어링·브리프 생성·학습)는 매일/매주/분기 주기로 실행되는 파이프라인이고, API 서버는 대시보드·태깅·CRM 파일 요청에 상시 응답한다. 둘은 같은 저장소·DB 스키마를 공유하되 프로세스는 분리한다.
- **판단은 코드, 문장은 AWS Bedrock AI Agent** (`2-prd.md` v1.2.0 5장 아키텍처 결정). 배치의 스코어링·배제·임계치 판정 단계에는 어떤 생성형 AI 호출도 두지 않는다. Bedrock AI Agent는 브리프·캠페인 문구 생성 단계에서만, Action Group(도구)과 Knowledge Base(RAG)를 통해서만 호출한다.
- **백엔드**: Python 3.12 + FastAPI + psycopg(ORM 미사용, 직접 SQL). **프론트엔드**: React 19 + TypeScript + Zustand(클라이언트 상태) + TanStack Query(서버 상태). **DB**: PostgreSQL 17.
- 과도한 추상화·설계는 금지한다. 배치 오케스트레이션 프레임워크(Airflow, Prefect 등), 이벤트 버스, 마이크로서비스 분리는 이 프로젝트 규모(단일 배치 SLA, 지점 수백 단위)에 맞지 않으므로 도입하지 않는다.

---

## 1. 최상위 공통 원칙

| 식별자 | 원칙 | 설명 |
|---|---|---|
| PRIN-01 | 실용주의 (MVP 우선) | `2-prd.md` 3장의 필수(Must) 항목(REQ-01, 02, 03, 05, 06, 07, 08, 14, 15)을 먼저 완성하고, 권장/선택 항목은 착수하지 않는다. |
| PRIN-02 | 오버엔지니어링 금지 (YAGNI) | 도메인 정의서·PRD에 없는 기능(범용 신호 플러그인 프레임워크, 다중 LLM 벤더 추상화 등)은 지금 만들지 않는다. |
| PRIN-03 | 관심사 분리 | 배치는 수집(connector)·정규화(normalizer)·판정(sensing)·채점(targeting)·생성(briefing)·학습(learning)을 레이어별로 분리한다. API는 라우팅·비즈니스 로직·데이터 접근을 분리한다. |
| PRIN-04 | 단일 책임 | 커넥터 하나는 소스 하나만 담당한다. 서비스는 비즈니스 로직만, 리포지토리는 SQL 실행만 담당한다. |
| PRIN-05 | 명시적 계약 | 배치 단계 간 데이터 전달은 Pydantic 모델(`common/schemas/`)로 명시하고, API 요청/응답도 동일하게 Pydantic으로 검증한다. |
| PRIN-06 | 일관된 에러 처리 | API는 공통 에러 응답 형식(`{ "error": { "code", "message" } }`)을 모든 엔드포인트에서 동일하게 사용한다. 배치는 소스별 실패를 격리하고 RULE-SENSE-04(전일 스냅샷 폴백)로 흡수한다. |
| PRIN-07 | 단일 진실 공급원 | 서버 데이터(추천, 브리프, 태깅, 가중치 등)는 TanStack Query 캐시가 프론트엔드의 단일 진실 공급원이며, Zustand는 서버 데이터를 중복 보관하지 않는다. |
| PRIN-08 | 재현성 우선 | 배치 각 단계는 입력(스냅샷 ID, 임계치 버전, 가중치 버전)을 명시적으로 받아 순수 함수에 가깝게 동작해야 한다. 같은 입력이면 같은 출력이 나와야 한다(`2-prd.md` 6장 재현성 요건). |

---

## 2. 의존성/레이어 원칙

### 공통 규칙

| 식별자 | 원칙 |
|---|---|
| DEP-01 | 상위 레이어는 하위 레이어에 의존할 수 있으나, 하위 레이어는 상위 레이어를 알지 못한다. |
| DEP-02 | 같은 레이어 내 모듈 간 순환 참조를 금지한다. |
| DEP-03 | 레이어를 건너뛰는 직접 호출을 금지한다 (예: API 라우터가 리포지토리를 직접 호출하지 않고 반드시 서비스를 경유; 배치의 채점 단계가 커넥터를 직접 호출하지 않고 반드시 정규화된 SIGNAL을 경유). |

### 배치 파이프라인 레이어 (일간 실행 흐름)

```
connectors (소스별 원본 수집, DATA_SOURCE_SNAPSHOT 적재)
  → normalizers (SIGNAL로 정규화, 기준일 부여)
    → sensing (임계치 판정 → EVENT 승격, RULE-SENSE-01~05)
      → targeting (배제 → 스코어링 → TOP 20, 그중 3건은 탐색 슬롯, RULE-TARGET-01~06)
        → briefing (AWS Bedrock AI Agent 호출로 BRIEF 생성, RULE-BRIEF-01~03)
          → export (CRM 파일 생성, DB 저장)
```

- `connectors`는 소스 API 호출과 원본 응답의 스냅샷 적재만 담당한다. 정규화 로직을 포함하지 않는다.
- `sensing`은 도메인 정의서 5.1절(이벤트 승격 판정) 순서를 그대로 구현하는 유일한 위치다.
- `targeting`은 RULE-TARGET-02 스코어링 공식(신선도 항 R 포함, RULE-TARGET-05)과 RULE-TARGET-03 탐색 슬롯 배정, RULE-TARGET-06 사유 계층 분류를 구현한다. Bedrock을 호출하지 않으며, 이미 `population`이 적재한 BUSINESS를 읽기만 한다(REQ-16, UC-17 선행 조건).
- `briefing`은 확정된 RECOMMENDATION을 입력받아 문장을 생성하며, Bedrock AI Agent의 Action Group(도구)·Knowledge Base(RAG)로 조회한 값 외의 사실을 인용하면 안 된다(RULE-BRIEF-02). 이 검증(citation guard)은 briefing 내부에서 자체 완결되어야 한다.
- 학습(`learning`)과 캠페인(`campaign`)은 각각 주간·이벤트 트리거 배치로 별도 진입점을 가지며, 위 일간 파이프라인과 프로세스를 공유하지 않는다.
- **`population`은 일간 파이프라인에 속하지 않는다.** 월 1회 `run_monthly.py`로 실행되며, 일간 배치는 이미 적재된 BUSINESS를 읽기만 한다. 모집단 적재 실패가 일간 07:30 SLA를 침해하지 않도록 프로세스를 분리한다(REQ-16, UC-17).

### API 서버 레이어 (요청 처리 흐름)

```
routers (라우팅 정의)
  → services (비즈니스 로직: 태깅 저장, 임계치 변경, 승인 흐름)
    → repositories (SQL 직접 실행)
      → db (커넥션 풀)
```

- 라우터는 URL과 서비스 호출을 연결하는 역할만 한다.
- 서비스는 도메인 규칙(RULE-BRANCH, RULE-CAMPAIGN 등 API에서 트리거되는 규칙)을 구현하는 유일한 위치다.
- 리포지토리는 SQL 실행과 결과 매핑만 담당한다.
- 인증/권한 검증(JWT 검증, 역할·소속 지점 기반 접근 제어)은 미들웨어에서 공통 처리한다.

### 프론트엔드 레이어 (데이터 흐름)

```
components / pages (UI 렌더링)
  → stores (Zustand: 로그인 여부, 필터 선택 등 클라이언트 전용 상태)
  → queries (TanStack Query: 추천/브리프/태깅/임계치/캠페인 등 서버 상태)
    → api (API 클라이언트: fetch 래퍼, 엔드포인트 호출 함수)
```

- **Zustand**: 서버에 저장되지 않는 순수 클라이언트 상태만 다룬다 (로그인 토큰, 선택된 상태 필터, 사이드바 열림 여부 등).
- **TanStack Query**: 서버로부터 가져오거나 반영해야 하는 데이터(추천 목록, 브리프, 태깅, 임계치, 캠페인, 채택률 통계)를 다룬다.
- 컴포넌트는 API 클라이언트를 직접 호출하지 않고 반드시 TanStack Query 훅을 통해 데이터에 접근한다.

---

## 3. 코드/네이밍 원칙

### 공통

| 식별자 | 대상 | 규칙 |
|---|---|---|
| NAME-01 | 파일명 | 기능 단위로 이름을 부여한다. 의미 없는 축약어를 쓰지 않는다. |
| NAME-02 | 도메인 용어 일치 | 코드 상 변수·함수명은 도메인 정의서의 한국어 개념을 영어로 직역해 통일한다 (신호=`signal`, 이벤트=`event`, 추천=`recommendation`, 태깅=`tag_feedback`, 가중치=`signal_weight`, 탐색 슬롯=`exploration_slot`). |

### 백엔드 (Python)

| 식별자 | 대상 | 규칙 |
|---|---|---|
| NAME-B01 | 파일명 | `snake_case` (예: `permit_connector.py`, `event_promoter.py`, `weight_updater.py`). |
| NAME-B02 | 함수명 | `snake_case`, 동사로 시작 (예: `fetch_daily_signals`, `promote_event`, `score_recommendation`). |
| NAME-B03 | 커넥터 함수 | 소스명을 그대로 드러낸다 (예: `nts_connector.fetch_business_status`, `permit_connector.fetch_all_businesses`, `permit_connector.fetch_daily_changes`). 한 소스가 모집단과 신호 두 역할을 하는 경우 함수를 분리하고, 함수명에 역할을 드러낸다. 커넥터 이름은 **데이터의 정체**(예: 지방행정 인허가)를 따르며, 포털·호스트명(예: 옛 `localdata_connector`)을 따르지 않는다 — 취득처가 바뀌어도 이름이 거짓말이 되지 않게 한다 |
| NAME-B04 | 타입 표기 | Pydantic 모델로 배치 단계 간 데이터, API 요청/응답을 정의한다 (`common/schemas/`). |

### 프론트엔드 (TypeScript)

| 식별자 | 대상 | 규칙 |
|---|---|---|
| NAME-F01 | 컴포넌트 파일/함수명 | `PascalCase` (예: `RecommendationCard.tsx`, `ThresholdEditor.tsx`). |
| NAME-F02 | 훅 파일/함수명 | `camelCase`, `use` 접두사 (예: `useRecommendations.ts`, `useTagMutation.ts`). |
| NAME-F03 | Zustand 스토어 | `camelCase` + `Store` 접미사 (예: `authStore.ts`, `filterStore.ts`). |
| NAME-F04 | 타입/인터페이스 | `PascalCase` (예: `Recommendation`, `Brief`, `SignalWeight`). API 응답 타입은 `src/types/`에 모아 정의한다. |
| NAME-F05 | TanStack Query 키 | 도메인 단위 배열 (예: `['recommendations', branchId, date]`, `['thresholds']`). |

---

## 4. 테스트/품질 원칙

리스크가 높은 로직(판정·스코어링·학습)에 테스트를 집중하고, 단순 CRUD는 실용적으로 처리한다.

| 식별자 | 원칙 |
|---|---|
| TEST-01 | 우선순위 1: 이벤트 승격 판정(도메인 정의서 5.1절)은 임계치 경계값·쿨다운 경계·상한 절사 케이스를 포함한 단위 테스트를 반드시 작성한다. |
| TEST-02 | 우선순위 2: 배제 우선순위(RULE-TARGET-01), 스코어링 공식(RULE-TARGET-02), 채택률·가중치 계산(도메인 정의서 5.2절)은 경계값(표본 30건 미만, 클리핑 상하한)을 포함한 단위 테스트를 작성한다. |
| TEST-03 | 우선순위 3: 브리프 생성의 그라운딩 검증(RULE-BRIEF-02, 근거 없는 문장 차단)은 회귀 테스트셋으로 주기 검증한다(`2-prd.md` 6장). |
| TEST-04 | 그 외 단순 CRUD 엔드포인트(지점 등록·수정, 태깅 저장, 임계치 저장 등)는 통합 테스트 또는 수동 확인(Postman/curl)으로 검증한다. |
| TEST-05 | 프론트엔드는 별도 단위 테스트를 강제하지 않는다. `3-user-scenario.md`의 SC-01~08 흐름 기준 수동 확인으로 검증한다. |
| TEST-06 | 배치 전체는 재현성 검증을 위해, 동일한 스냅샷·임계치·가중치 버전을 입력했을 때 동일한 RECOMMENDATION·BRIEF가 산출되는지 분기 단위로 검증한다(PRIN-08). |
| TEST-07 | 백엔드는 ruff(린트) + mypy(타입 검사)를 최소 수준으로 적용한다. 프론트엔드는 ESLint + Prettier를 사용한다. |

---

## 5. 설정/보안/운영 원칙

| 식별자 | 원칙 |
|---|---|
| OPS-01 | 환경변수 관리 | DB 접속 정보, JWT 시크릿, 각 공공데이터 API 인증키는 `.env`로 관리하고 코드에 하드코딩하지 않는다. AWS Bedrock 접근은 API 키가 아니라 IAM 역할/자격증명(리전, Agent ID, Knowledge Base ID 포함)으로 관리하며, 로컬 개발 시에도 장기 액세스 키를 코드에 하드코딩하지 않는다. `.env.example`로 필요한 키 목록만 공유한다. |
| OPS-02 | DB 커넥션 풀 | psycopg의 커넥션 풀을 배치 프로세스와 API 프로세스 각각 시작 시 1회 생성해 재사용한다. |
| OPS-03 | 인증/인가 | 모든 인증 필요 API는 공통 인증 미들웨어에서 JWT를 검증한다. 역할·소속 지점 기반 접근 제어(RM은 본인 소속 지점 데이터만, VAL-08)는 서비스 레이어에서 수행한다. 본부 역할은 마케팅/준법 하위 역할로 구분되며(VAL-08), 캠페인 준법 승인(`campaign.service.py`)은 본부(준법) 역할만 호출 가능하도록 이 레이어에서 검증한다(RULE-CAMPAIGN-01). |
| OPS-04 | 배치 실패 격리 | 소스 커넥터 하나의 실패가 전체 배치를 중단시키지 않는다. 실패한 소스만 RULE-SENSE-04(전일 스냅샷 폴백)를 적용하고 나머지는 정상 진행한다. |
| OPS-05 | 스냅샷 보존 | `DATA_SOURCE_SNAPSHOT`은 날짜 파티션으로 적재하며, 감사 추적(REQ-15) 및 재현성 검증(TEST-06)을 위해 최소 1년 보존한다. |
| OPS-06 | 생성형 AI 호출 격리 | AWS Bedrock AI Agent 호출은 `briefing`/`campaign` 모듈에서만 발생하며, Agent에 등록된 어떤 Action Group·Knowledge Base도 개인 고객정보·거래정보를 반환하지 않는다(RULE-SEC-01). |
| OPS-07 | CORS | 프론트엔드 배포 origin만 허용한다. 와일드카드(`*`) 허용은 프로덕션에서 사용하지 않는다. |
| OPS-08 | 로깅 | 배치는 단계별 처리 건수·소요시간·실패 소스를 구조화 로그로 남긴다. API는 요청 단위 기본 로그(메서드, 경로, 상태 코드, 응답 시간)만 남긴다. |
| OPS-09 | 마이그레이션 | ORM 없이 순수 SQL로 스키마를 관리한다. 저장소 루트의 `database/schema.sql` 단일 파일에 전체 스키마를 정의하고 psql로 직접 실행한다. |

---

## 6. 디렉토리 구조

### 백엔드 (Python 3.12 + FastAPI + psycopg, ORM 없음)

```
backend/
├── batch/
│   ├── connectors/                 # 소스별 원본 수집 (스냅샷 적재만 담당)
│   │   ├── nts_connector.py         # 국세청 사업자등록상태 (REQ-02, 보완 검증)
│   │   ├── permit_connector.py      # 행안부 지방행정 인허가 — fetch_all_businesses(전수)/fetch_daily_changes(변동분) 2함수 (REQ-16, REQ-03)
│   │   ├── sbiz_connector.py        # 소진공 상가(상권)정보 (REQ-04)
│   │   ├── subway_connector.py      # 서울/부산 등 지하철 승하차 (REQ-03)
│   │   ├── ecos_connector.py        # 한국은행 ECOS (REQ-03, REQ-11)
│   │   ├── opinet_connector.py      # 오피넷 유가정보 (REQ-03, REQ-11)
│   │   ├── kma_connector.py         # 기상청 특보 (REQ-03, REQ-10, REQ-12)
│   │   └── disaster_msg_connector.py # 행안부 긴급재난문자 (REQ-12)
│   ├── population/                 # 사업체 모집단 적재 (REQ-16, UC-17)
│   │   └── business_loader.py
│   ├── normalizers/                # 소스별 원본 → SIGNAL 정규화
│   │   └── signal_normalizer.py
│   ├── sensing/                    # 이벤트 승격 판정 (도메인 정의서 5.1절)
│   │   ├── threshold_engine.py
│   │   └── event_promoter.py
│   ├── targeting/                  # 배제·스코어링(신선도 항 포함)·사유 계층·탐색 슬롯 (RULE-TARGET)
│   │   ├── exclusion.py
│   │   ├── scorer.py               # RULE-TARGET-02/05 (Score, 신선도 항 R)
│   │   ├── reason_tier.py           # RULE-TARGET-06 사유 계층 분류
│   │   └── exploration.py
│   ├── briefing/                   # AWS Bedrock AI Agent 브리프 생성 (RULE-BRIEF)
│   │   ├── bedrock_agent_client.py  # Bedrock Agent 호출 래퍼 (Action Group·Knowledge Base 연동)
│   │   ├── brief_generator.py
│   │   └── citation_guard.py        # 근거 없는 문장 차단 (RULE-BRIEF-02)
│   ├── learning/                   # 채택률 집계 및 가중치 갱신 (RULE-LEARN)
│   │   ├── adoption_metrics.py
│   │   └── weight_updater.py
│   ├── campaign/                   # 캠페인 트리거·초안 생성 (Phase 3, RULE-CAMPAIGN)
│   │   ├── trigger.py
│   │   └── draft_generator.py
│   ├── run_daily.py                 # 07:30 SLA 대상 파이프라인 진입점
│   ├── run_weekly.py                 # 가중치 갱신 배치 진입점
│   ├── run_monthly.py                # 모집단 적재 배치 진입점 (UC-17)
│   └── run_quarterly.py              # 분기 신호 배치 진입점
├── api/
│   ├── routers/
│   │   ├── branches.router.py
│   │   ├── recommendations.router.py
│   │   ├── tags.router.py
│   │   ├── thresholds.router.py
│   │   ├── campaigns.router.py
│   │   └── adoption.router.py
│   ├── services/
│   │   ├── branch.service.py
│   │   ├── tag.service.py           # 태깅 저장 (RULE-LEARN-01/02)
│   │   ├── threshold.service.py     # 임계치·가중치 관리자 설정 (REQ-14)
│   │   └── campaign.service.py      # 승인 흐름 (RULE-CAMPAIGN-01)
│   ├── repositories/
│   │   ├── branch.repository.py
│   │   ├── recommendation.repository.py
│   │   ├── tag.repository.py
│   │   └── campaign.repository.py
│   ├── middlewares/
│   │   ├── auth.middleware.py
│   │   └── error.middleware.py
│   └── app.py
├── common/
│   ├── config.py                    # .env 로드
│   ├── geo.py                        # EPSG:5174 → WGS84 좌표 변환 (VAL-11)
│   ├── db/
│   │   └── pool.py
│   ├── schemas/                     # Pydantic 모델 (배치 단계 간 계약, API 요청/응답)
│   │   ├── signal.py
│   │   ├── event.py
│   │   ├── recommendation.py
│   │   ├── brief.py
│   │   └── business.py               # BUSINESS 모집단 적재 계약 (REQ-16)
│   └── snapshot_store.py            # DATA_SOURCE_SNAPSHOT 적재/조회
├── database/
│   └── schema.sql
├── .env.example
└── pyproject.toml
```

### 프론트엔드 (React 19 + TypeScript + Zustand + TanStack Query)

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts                 # 공통 fetch 래퍼 (baseURL, 토큰 헤더, 에러 파싱)
│   │   ├── auth.api.ts
│   │   ├── branch.api.ts
│   │   ├── recommendation.api.ts
│   │   ├── brief.api.ts
│   │   ├── tag.api.ts
│   │   ├── threshold.api.ts
│   │   ├── campaign.api.ts
│   │   └── adoption.api.ts
│   ├── queries/
│   │   ├── useAuth.ts
│   │   ├── useBranch.ts
│   │   ├── useRecommendations.ts
│   │   ├── useBrief.ts
│   │   ├── useTagMutation.ts
│   │   ├── useThresholds.ts
│   │   ├── useCampaigns.ts
│   │   └── useAdoptionStats.ts
│   ├── stores/
│   │   ├── authStore.ts
│   │   └── filterStore.ts            # 선택된 지점/기간/상태 필터 등 클라이언트 상태
│   ├── components/
│   │   ├── branch/
│   │   │   └── BranchSetupForm.tsx
│   │   ├── recommendation/
│   │   │   ├── RecommendationList.tsx
│   │   │   ├── RecommendationCard.tsx
│   │   │   └── TagButtons.tsx
│   │   ├── brief/
│   │   │   └── BriefDetail.tsx
│   │   ├── operations/
│   │   │   └── ForecastPanel.tsx
│   │   ├── campaign/
│   │   │   ├── CampaignBoard.tsx
│   │   │   └── CampaignDraftReview.tsx
│   │   ├── admin/
│   │   │   ├── ThresholdEditor.tsx
│   │   │   └── AdoptionDashboard.tsx
│   │   └── common/
│   │       ├── Button.tsx
│   │       ├── DataTable.tsx
│   │       ├── StatTile.tsx
│   │       ├── StatusBadge.tsx
│   │       ├── Tabs.tsx              # 상태 필터용 밑줄 탭 (8-wireframe.md §4, 9-style-guide.md §5.7)
│   │       ├── TopUtilityBar.tsx     # 사용자명·세션 타이머·보조 링크 (8-wireframe.md §1, 9-style-guide.md §5.8)
│   │       └── Layout.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── BranchSetupPage.tsx
│   │   ├── DashboardPage.tsx         # 오늘의 접촉 TOP 20 (UC-06)
│   │   ├── BriefDetailPage.tsx        # UC-07
│   │   ├── OperationsPage.tsx         # UC-11
│   │   ├── CampaignBoardPage.tsx      # UC-12~14
│   │   ├── AdminThresholdPage.tsx     # UC-15
│   │   └── AdoptionDashboardPage.tsx  # UC-16
│   ├── types/
│   │   ├── branch.ts
│   │   ├── recommendation.ts
│   │   ├── brief.ts
│   │   ├── campaign.ts
│   │   └── adoption.ts
│   ├── router.tsx
│   └── main.tsx
├── package.json
└── tsconfig.json
```

> 위 트리는 REQ-01~16 및 UC-01~17을 구현하는 데 필요한 최소 단위로 구성했다. 이 범위를 넘어서는 디렉토리(예: `domain/`, `infrastructure/` 등 계층형 아키텍처 폴더, 배치 오케스트레이션 도구용 폴더)는 PRIN-01·PRIN-02에 따라 도입하지 않는다.

---

## 7. 참고 문서

- `1-domain-definition.md` (v1.2.0): REQ, VAL, 엔티티, RULE, 핵심 계산값 정의, UC
- `2-prd.md` (v1.2.0): 기술 스택(5장), 비기능 요건(6장), 범위 우선순위(3장)
- `3-user-scenario.md` (v1.1.0): 시나리오 SC-01~08
