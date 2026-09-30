# C-MAKER AWS 배포 인프라 분석 보고서

- **작성일**: 2026-09-29
- **개정일**: 2026-09-30 (v2.0.0)
- **대상 프로젝트**: C-MAKER (영업점 신호 감지 + 접촉 명부 추천 시스템)
- **분석 범위**: `agents/*.md` 에이전트 정의, `docs/*` 프로젝트 문서, `backend/`·`frontend/` 소스 구성

### 개정 이력

| 버전 | 일자 | 변경 내용 |
|---|---|---|
| v1.0.0 | 2026-09-29 | 최초 작성 (EC2 2대 + RDS + Bedrock 직접 호출 가정) |
| v2.0.0 | 2026-09-30 | **LLM 경로를 LiteLLM Gateway로 정정**(실호출 검증 완료). 제품명 C-MAKER 반영, 현행 단일 EC2 구성과 확장 구성을 §1.3에서 분리, 런타임 버전 현행화(Python 3.14.4 / PostgreSQL 18.6 / Node v24), Bedrock 직접 연동 전제의 IAM Role·AI Agent·Knowledge Base 작업 항목 제거 |
| v2.0.1 | 2026-09-30 | **EC2 실연동 검증 반영.** v2.0.0의 "UC-07 5초 미달성" 판단을 철회 — 개발 PC 지연(7.4초)을 근거로 삼은 오판이었고, EC2 실측은 median 3.77초로 충족한다(§4.2). 타임아웃 권장값 15초 → 10초 |

> **이 보고서의 위치**
> `docs/10-implementation-guide.md`(v2.2.0)가 **현재 배포된 단일 EC2 구성의 최종 기준**이다.
> 본 보고서는 그 위에서 **AWS 확장 구성(EC2 분리 + RDS)으로 갈 때의 참고 설계**를 다룬다.
> 두 문서가 충돌하면 `10-implementation-guide.md`를 따른다.

---

## 목차

1. [프로젝트 구성 요약](#1-프로젝트-구성-요약)
2. [에이전트(agents/*.md) 분석 결과](#2-에이전트-분석-결과)
3. [AWS 인프라 구성도](#3-aws-인프라-구성도)
4. [프로세스 흐름도](#4-프로세스-흐름도)
5. [GitHub를 통한 배포 방법](#5-github를-통한-배포-방법)
6. [공공 API 호출 — 2가지 케이스 비교 분석](#6-공공-api-호출--2가지-케이스-비교-분석)
7. [배포를 위한 필수 작업 목록](#7-배포를-위한-필수-작업-목록)
8. [비용 추정 및 권장 사양](#8-비용-추정-및-권장-사양)

---

## 1. 프로젝트 구성 요약

### 1.1 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| **Frontend** | React 19 + TypeScript + Zustand + TanStack Query | Vite 빌드, SPA. `serve -s`로 정적 서빙 |
| **Backend (API)** | Python 3.14 + FastAPI | Uvicorn ASGI (`:8000`), systemd 관리 |
| **Backend (Batch)** | Python 3.14 | 일간/월간 배치 + 지오코딩 잡, cron |
| **DB 접근** | psycopg 3 (직접 SQL, ORM 미사용) | `psycopg[binary]` + `psycopg_pool` |
| **DB** | PostgreSQL 18.6 | 현행: EC2 localhost. 확장 시 RDS |
| **LLM** | **LiteLLM Gateway (OpenAI-Compatible)** → 백엔드는 Bedrock | `openai` 패키지로 호출. §1.2 참조 |
| **공공 데이터** | data.go.kr 등 8종 API | 국세청, 행안부, 기상청 등 |

> **런타임 버전 주의** — 설계 문서(`2-prd.md` 등)는 Python 3.12 / PostgreSQL 17을 적고 있으나, 실제 서버는 Ubuntu 26.04.1 LTS 기본 제공인 **Python 3.14.4 / PostgreSQL 18.6**이다. `backend/requirements.txt`는 3.14에서 설치 검증된 버전으로 고정되어 있다(`pydantic==2.13.5`, `PyJWT` 등).

### 1.2 LLM 경로 — Bedrock 직접 호출이 아니다

v1.0.0에서는 EC2가 Bedrock을 직접 호출하는 것으로 기술했으나, **실제 제공 환경은 사내 LiteLLM Gateway**다. 2026-09-30 실호출로 확인한 내용:

| 항목 | 값 |
|---|---|
| Endpoint | `POST https://frontier-llmgw.aipocnhbank.com/v1/chat/completions` |
| 프로토콜 | OpenAI-Compatible Chat Completions |
| 인증 | LiteLLM Virtual Key — `Authorization: Bearer sk-...` |
| 모델 | `claude-opus-5` (그 외 `claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5-20251001-v1:0` 등) |
| 라이브러리 | `openai==1.109.1` (`base_url`을 `.../v1`로 지정) |
| 호출 지점 | `backend/batch/briefing/llm_client.py` (OPS-06 — briefing 모듈 단독) |

게이트웨이의 모델 ID가 `global.anthropic.claude-opus-5`로 반환되고 모델 목록에 `amazon.titan-embed-text-v2:0`, `nova-2-lite-v1:0`, `stability.stable-image-ultra-v1:1`이 포함되어 있어, **게이트웨이 뒤가 Bedrock**임은 확인된다. 다만 EC2 관점에서는 HTTPS(443) 아웃바운드 한 줄이 전부다.

**배포 영향:**

- **EC2 → Bedrock IAM Role 불필요.** 인증을 게이트웨이가 중계한다. `boto3`도 의존성에 없다.
- **Bedrock AI Agent / Knowledge Base 구성 작업 불필요.** 일반 Chat Completions만 사용한다.
- **VPC PrivateLink 대상이 Bedrock이 아니라 게이트웨이**다. 보안 검토 대상이 바뀐다(§7.4).
- **AWS 비용에 Bedrock 항목이 잡히지 않는다.** 게이트웨이 사용료의 청구 주체는 별도 확인이 필요하다(§8.1).

게이트웨이 제약과 그에 따른 코드 대응은 `docs/10-implementation-guide.md` §8.2에 정리되어 있다(요약: `temperature=0` 거부 → 미전송, extended thinking 기본 ON → `thinking: {"type": "disabled"}` 전달, 타임아웃 10초).

**EC2 연동 검증 완료 (2026-09-30)** — `ip-10-49-0-19`에서 `generate_brief()`를 직접 실행해 브리프 5건을 생성했고, 전부 `generation_status="LLM"`으로 통과했다(TEMPLATE 폴백 없음). DNS 해석·아웃바운드 443·Virtual Key 인증 모두 정상이며 프록시 설정은 필요하지 않았다. 상세는 `docs/10-implementation-guide.md` §8.4~8.5.

### 1.3 현행 구성과 확장 구성

| 구분 | 현행 (배포됨) | 확장 (본 보고서 §3 이하 제안) |
|---|---|---|
| 서버 | **EC2 단일 인스턴스** (Ubuntu 26.04.1) | EC2 2대 (Frontend / Backend 분리) |
| 프론트엔드 | `serve -s` (`:8080`), Nginx 리버스 프록시 | Nginx 정적 서빙 |
| DB | EC2 localhost PostgreSQL 18.6, 기존 `myapp_db` 재사용 | RDS PostgreSQL, Private Subnet |
| 네트워크 | 기본 VPC, 인바운드 80/22 | 전용 VPC, Public/Private Subnet × 2 AZ |
| LLM | LiteLLM Gateway (HTTPS 아웃바운드) | 동일 |

현행 구성의 상세(포트 배치, Nginx 설정, systemd, cron)는 `docs/10-implementation-guide.md` §1~2에 있다. **§3 이하는 확장 구성 기준**으로 읽어야 한다.

### 1.4 주요 데이터 소스 (공공 API)

| 소스 | 제공기관 | 갱신 주기 | 용도 |
|------|----------|----------|------|
| 사업자등록상태 조회 | 국세청 | 실시간 (30분 반영) | 휴·폐업 검증 |
| 지방행정 인허가 전수 | 행안부 | 월 1회 | 사업체 모집단 |
| 지방행정 인허가 변동분 | 행안부 | 일 | 신규 개업·폐업 신호 |
| 상가(상권)정보 | 소진공 | 분기 | 업종별 점포 증감 |
| 지하철 승하차 인원 | 서울/부산 등 | 일 (T+3~5) | 유동인구 프록시 |
| ECOS Open API | 한국은행 | 일·월 혼재 | 환율·금리·BSI |
| 오피넷 유가정보 | 한국석유공사 | 일 | 유가 신호 |
| 기상특보 조회 | 기상청 | 수시 | 내점·현금 수요 예측 |

---

## 2. 에이전트 분석 결과

### 2.1 에이전트 목록 및 역할

`agents/` 디렉토리에 총 11개 에이전트 정의 파일이 존재합니다.

| 에이전트 | 모델 | C-MAKER 배포와의 관련도 | 역할 요약 |
|----------|------|--------------------------|----------|
| **backend-developer** | sonnet | ⭐⭐⭐ 높음 | FastAPI API·배치 구현, 배포 파이프라인 |
| **frontend-developer** | sonnet | ⭐⭐⭐ 높음 | React SPA 개발, 빌드·배포 구성 |
| **api-designer** | sonnet | ⭐⭐⭐ 높음 | REST API 설계, OpenAPI 문서화 |
| **fullstack-developer** | sonnet | ⭐⭐ 중간 | DB→API→Frontend 전 레이어 통합 |
| **ui-designer** | sonnet | ⭐⭐ 중간 | 디자인 시스템·접근성·반응형 설계 |
| **microservices-architect** | inherit | ⭐ 낮음 | 현재 모놀리식 구조, Phase 이후 참고 가능 |
| **graphql-architect** | inherit | ⭐ 낮음 | 현재 REST 기반, 해당 없음 |
| **websocket-engineer** | sonnet | ⭐ 낮음 | 실시간 기능 Phase 2+ 참고 |
| **mobile-developer** | sonnet | — 해당 없음 | 웹 전용 프로젝트 |
| **electron-pro** | sonnet | — 해당 없음 | 데스크톱 앱 해당 없음 |
| **design-bridge** | inherit | — 해당 없음 | 디자인 번역 전용 |

### 2.2 배포 관점 핵심 에이전트 시사점

**backend-developer** 에이전트에서 정의하는 배포 관련 주요 사항:
- Docker 멀티스테이지 빌드, 컨테이너 health check
- 환경별 설정 분리 (dev/prod — `APP_ENV`)
- 시크릿 관리, 기능 플래그
- Prometheus 메트릭, OpenTelemetry 분산 추적
- 로그 구조화 (correlation ID 포함)

> 현행 배포는 컨테이너가 아니라 **systemd + venv 직접 실행**이다(`deploy/c-maker-api.service`). Docker 관련 항목은 향후 선택지로만 본다.

**frontend-developer** 에이전트에서 정의하는 빌드/배포 사항:
- TypeScript strict mode, 번들 최적화
- 빌드 파이프라인 및 배포 프로세스
- Storybook 문서화, 성능 메트릭

**api-designer** 에이전트에서 정의하는 API 표준:
- OpenAPI 3.1 명세, JWT 인증
- Rate limiting, CORS 설정 (와일드카드 금지 — OPS-07)
- API 버저닝 전략

---

## 3. AWS 인프라 구성도 (확장 구성)

### 3.1 전체 구성도

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   AWS Cloud (ap-northeast-2, 서울 리전)                   │
│                                                                                          │
│  ┌─ AWS WorkSpaces ─────────┐                                                           │
│  │                           │                                                           │
│  │  개발자 데스크톱            │──── GitHub Push ────┐                                     │
│  │  (코드 개발 + git 관리)     │                      │                                     │
│  │                           │                      │                                     │
│  └───────────────────────────┘                      │                                     │
│                                                      ▼                                     │
│                                           ┌─ GitHub ──────────┐                           │
│                                           │  Repository        │                           │
│                                           │  (main / develop)  │                           │
│                                           └────┬──────────────┘                           │
│                                                │                                           │
│                                    GitHub Actions (CI/CD)                                  │
│                                    ┌───────────┴───────────┐                               │
│                                    │                       │                               │
│                                    ▼                       ▼                               │
│  ┌─ VPC (10.0.0.0/16) ─────────────────────────────────────────────────────────────────┐ │
│  │                                                                                       │ │
│  │  ┌─ Public Subnet (10.0.1.0/24) ────────────────────────────────────────────────┐   │ │
│  │  │                                                                                │   │ │
│  │  │  ┌─ EC2: Frontend ────────────┐    ┌─ EC2: Backend ──────────────────────┐    │   │ │
│  │  │  │                             │    │                                      │    │   │ │
│  │  │  │  Nginx                      │    │  Nginx (리버스 프록시)                │    │   │ │
│  │  │  │   └─ Static Files           │    │   └─ FastAPI (Uvicorn :8000)        │    │   │ │
│  │  │  │      (React 빌드 산출물)      │    │       ├─ API 서버 (routers →        │    │   │ │
│  │  │  │                             │    │       │   services → repositories)   │    │   │ │
│  │  │  │  Port: 80, 443             │    │       └─ 배치 프로세스                 │    │   │ │
│  │  │  │                             │    │           (connectors → normalizers   │    │   │ │
│  │  │  │                             │    │            → sensing → targeting      │    │   │ │
│  │  │  │                             │    │            → briefing)               │    │   │ │
│  │  │  │                             │    │                                      │    │   │ │
│  │  │  │                             │    │  Port: 80, 443, 8000                │    │   │ │
│  │  │  └─────────────────────────────┘    └──────────────┬───────────────────────┘    │   │ │
│  │  │                                                     │                           │   │ │
│  │  └─────────────────────────────────────────────────────┼───────────────────────────┘   │ │
│  │                                                        │                               │ │
│  │  ┌─ Private Subnet (10.0.2.0/24) ─────────────────────┼───────────────────────────┐   │ │
│  │  │                                                     │                           │   │ │
│  │  │  ┌─ Amazon RDS ──────────────────────────────────┐  │                           │   │ │
│  │  │  │  PostgreSQL 18                                 │  │                           │   │ │
│  │  │  │  - Multi-AZ (선택)                              │◄─┘                           │   │ │
│  │  │  │  - 자동 백업 (7일 보존)                          │                              │   │ │
│  │  │  │  - Port: 5432                                  │                              │   │ │
│  │  │  └────────────────────────────────────────────────┘                              │   │ │
│  │  │                                                                                  │   │ │
│  │  └──────────────────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                                       │ │
│  └───────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────┬───────────────────────────────────────────────┘
                                            │ HTTPS 443 아웃바운드
              ┌─────────────────────────────┴──────────────────────────────┐
              ▼                                                             ▼
┌─ 사내 LiteLLM Gateway ─────────────────┐    ┌─ 외부 공공 API ──────────────────────┐
│  frontier-llmgw.aipocnhbank.com/v1     │    │  data.go.kr (인허가, 국세청 등)      │
│  OpenAI-Compatible Chat Completions    │    │  ECOS, 오피넷, 기상청 등             │
│  Virtual Key (Bearer) 인증              │    │                                     │
│    └─ (게이트웨이 백엔드: AWS Bedrock)   │    │  ※ EC2 Backend → HTTPS 아웃바운드    │
│  ※ PrivateLink 적용 여부 보안팀 확인     │    │                                     │
└────────────────────────────────────────┘    └─────────────────────────────────────┘
```

> **v1.0.0과의 차이** — 구성도에서 `AWS Bedrock (AI Agent + KB)` 박스를 제거하고, VPC 밖의 **사내 LiteLLM Gateway**로 교체했다. EC2는 Bedrock에 직접 접근하지 않는다.

### 3.2 네트워크 구성 상세

| 구성 요소 | CIDR / 설정 | 용도 |
|-----------|------------|------|
| VPC | 10.0.0.0/16 | 전체 네트워크 |
| Public Subnet A | 10.0.1.0/24 (AZ-a) | EC2 Frontend + Backend |
| Public Subnet B | 10.0.3.0/24 (AZ-c) | (고가용성 확장 시) |
| Private Subnet A | 10.0.2.0/24 (AZ-a) | RDS Primary |
| Private Subnet B | 10.0.4.0/24 (AZ-c) | RDS Standby (Multi-AZ) |
| Internet Gateway | — | EC2의 인터넷 접근 |
| NAT Gateway | — | (Private Subnet 필요 시) |

### 3.3 Security Group 설정

**Frontend EC2 Security Group**

| 방향 | 포트 | 소스/대상 | 용도 |
|------|------|----------|------|
| 인바운드 | 80, 443 | 0.0.0.0/0 | 웹 접속 |
| 인바운드 | 22 | WorkSpaces IP | SSH 접속 |
| 아웃바운드 | ALL | 0.0.0.0/0 | 전체 허용 |

**Backend EC2 Security Group**

| 방향 | 포트 | 소스/대상 | 용도 |
|------|------|----------|------|
| 인바운드 | 80, 443 | 0.0.0.0/0 | API 접속 |
| 인바운드 | 22 | WorkSpaces IP | SSH 접속 |
| 아웃바운드 | 443 | 0.0.0.0/0 | 공공 API + **LiteLLM Gateway** 호출 |
| 아웃바운드 | 5432 | RDS SG | DB 접속 |

**RDS Security Group**

| 방향 | 포트 | 소스/대상 | 용도 |
|------|------|----------|------|
| 인바운드 | 5432 | Backend EC2 SG | API·배치에서 DB 접근 |
| 인바운드 | 5432 | WorkSpaces SG | 운영자 psql 직접 접근 (REQ-01) |

> 현행 단일 EC2 구성의 SG는 `docs/10-implementation-guide.md` §1.2를 따른다(인바운드 80/22, 아웃바운드 443, 5432·8000·8080은 localhost 내부).

---

## 4. 프로세스 흐름도

### 4.1 일반 사용자 요청 흐름

```
사용자 (브라우저)
    │
    │ ① HTTPS 요청
    ▼
┌─ EC2: Frontend ─────────────┐
│  Nginx                       │
│   └─ React SPA (정적 파일)    │
│      index.html + JS/CSS     │
└──────────────┬───────────────┘
               │
               │ ② API 요청 (/api/*)
               │    JWT 토큰 포함
               ▼
┌─ EC2: Backend ──────────────┐
│  Nginx (리버스 프록시)         │
│   └─ FastAPI (Uvicorn)       │
│       ├─ JWT 인증 확인        │
│       ├─ Router              │
│       ├─ Service             │
│       └─ Repository          │
│            │                  │
│            │ ③ SQL 쿼리       │
│            ▼                  │
└────────────┼─────────────────┘
             │
             ▼
┌─ PostgreSQL 18 ─────────────┐
│  RECOMMENDATION, BRIEF,      │
│  BUSINESS, EVENT 등 조회      │
│  (현행: localhost / 확장: RDS)│
└──────────────────────────────┘
```

### 4.2 배치 파이프라인 흐름 (매일 07:30 SLA)

```
┌─ EC2: Backend ─────────────────────────────────────────────────────────────┐
│                                                                             │
│  cron (매일 06:00) 또는 수동 재연동 (REQ-17)                                 │
│       │                                                                     │
│       ▼                                                                     │
│  run_daily.py                                                              │
│       │                                                                     │
│       ├─ ① connectors ──────────────────┐                                  │
│       │     소스별 원본 수집                │                                  │
│       │     (data.go.kr, ECOS, 기상청 등)  │──→ 외부 공공 API (HTTPS 443)    │
│       │     + DATA_SOURCE_SNAPSHOT 적재   │                                  │
│       │                                   │                                  │
│       ├─ ② normalizers                    │                                  │
│       │     SIGNAL 정규화 + 기준일 부여      │                                  │
│       │                                   │                                  │
│       ├─ ③ sensing                        │                                  │
│       │     임계치 판정 → EVENT 승격         │                                  │
│       │                                   │                                  │
│       ├─ ④ targeting                      │                                  │
│       │     배제 → 스코어링 → TOP 20        │                                  │
│       │     (탐색 슬롯은 Phase 2)           │                                  │
│       │                                   │                                  │
│       ├─ ⑤ briefing ───────────────────┐  │                                  │
│       │     LiteLLM Gateway              │──→ frontier-llmgw (HTTPS 443)    │
│       │     POST /v1/chat/completions    │    └─ 게이트웨이 백엔드: Bedrock   │
│       │     + citation guard 검증        │                                   │
│       │     실패 시 TEMPLATE 정형 화법 폴백 │                                   │
│       │                                  │                                   │
│       └─ ⑥ DB 적재                       │                                   │
│             SIGNAL, EVENT, RECOMMENDATION,│                                   │
│             BRIEF, CRM 파일 사전 생성      │──→ PostgreSQL (5432)              │
│                                           │                                   │
│  07:30 이전 완료 (P95 SLA)                 │                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

> **브리프 1건 지연 (EC2 실측, 2026-09-30)** — median 3.77초 / max 4.61초 (n=5, `claude-opus-5`, thinking 비활성). `UC-07`의 "브리프 1건 5초 이내"를 **충족한다**.
>
> 게이트웨이 IP가 AWS 서울 리전(`3.39.77.44`, `43.202.16.2`)이라 EC2에서는 같은 리전 통신이 된다. 개발 PC에서 같은 호출이 7.4초였으므로 **로컬 수치로 SLA를 판단하면 미달로 오판한다.**
>
> ⚠ 다만 **07:30 배치 전체 SLA는 아직 미측정**이다. TOP 20 × 파일럿 지점 수만큼 곱해지므로, 지점 수가 확정되면 `run_daily.py` 전체 실행 시간을 측정해야 한다(`docs/10-implementation-guide.md` §17-7).

### 4.3 모집단 적재 흐름 (월 1회)

```
run_monthly.py  (매월 1일 01:00)
    │
    ├─ ① 지방행정 인허가 전수 데이터 수집 (CSV, PERMIT_FULL_DATA_DIR)
    │
    ├─ ② 좌표 변환 (EPSG:5174 → WGS84, pyproj / VAL-11)
    │
    ├─ ③ BUSINESS 테이블 UPSERT (permit_mgt_no 기준 병합)
    │
    └─ ④ 적재 기준월 기록
         → PostgreSQL

geocode_job.py  (10분 주기) — 지점 주소 → 좌표 (VWorld, RULE-BRANCH-03)
```

---

## 5. GitHub를 통한 배포 방법

### 5.1 브랜치 전략

```
main (production)
 │
 ├── develop (staging/통합 테스트)
 │    │
 │    ├── feature/REQ-xx-기능명
 │    ├── fix/이슈번호-수정내용
 │    └── hotfix/긴급수정
 │
 └── release/v1.x.x (릴리즈 준비)
```

### 5.2 CI/CD 파이프라인 (GitHub Actions)

```yaml
# .github/workflows/deploy.yml 구성 개요

# ── Trigger ──────────────────────────
# main 브랜치 push 시 production 배포
# develop 브랜치 push 시 staging 배포

# ── Frontend 배포 Job ────────────────
# 1. Checkout
# 2. Node.js 24 설정 (현행 서버 v24.21.0, 20 LTS 호환)
# 3. npm ci
# 4. npm run build (Vite 빌드)
# 5. SCP로 빌드 산출물을 EC2 frontend/dist/ 에 전송
# 6. SSH로 c-maker-frontend(serve) 재시작

# ── Backend 배포 Job ─────────────────
# 1. Checkout
# 2. Python 3.14 설정
# 3. pip install -r backend/requirements.txt
# 4. ruff check + pytest
# 5. SCP로 소스를 EC2에 전송
# 6. SSH로 c-maker-api(systemd) 재시작
```

### 5.3 GitHub Actions 워크플로우 상세

```
┌─ WorkSpaces ─────┐     ┌─ GitHub ──────────────────────────────────────────────────┐
│                   │     │                                                           │
│  git push         │────→│  Repository                                               │
│                   │     │     │                                                      │
└───────────────────┘     │     ▼                                                      │
                          │  GitHub Actions                                            │
                          │     │                                                      │
                          │     ├─ Lint + Type Check                                   │
                          │     │   ├─ ESLint (frontend)                               │
                          │     │   ├─ tsc --noEmit (frontend)                         │
                          │     │   └─ ruff (backend)                                  │
                          │     │                                                      │
                          │     ├─ Test                                                │
                          │     │   ├─ pytest (backend)                                │
                          │     │   └─ vitest (frontend, 추후)                          │
                          │     │                                                      │
                          │     ├─ Build                                               │
                          │     │   └─ npm run build (frontend → dist/)                │
                          │     │                                                      │
                          │     └─ Deploy                                              │
                          │         ├─ SCP dist/  → SSH systemctl restart frontend     │
                          │         └─ SCP src/   → SSH systemctl restart api          │
                          │                                                            │
                          └────────────────────────────────────────────────────────────┘
```

### 5.4 배포 시 필요한 GitHub 설정

| 항목 | 설정 위치 | 내용 |
|------|----------|------|
| **SSH Key** | GitHub → Settings → Secrets | EC2 접속용 private key |
| **EC2 Host** | GitHub → Settings → Secrets | EC2 Public IP 또는 도메인 |
| ~~**AWS Credentials**~~ | — | **불필요.** Bedrock 직접 호출이 없어 IAM 자격증명이 필요하지 않다(§1.2) |
| **Environment Vars** | GitHub → Settings → Variables | `VITE_API_BASE_URL` 등 빌드 환경변수 |
| **Branch Protection** | GitHub → Settings → Branches | main 브랜치 직접 push 방지, PR 필수 |

> `.env`(DB 비밀번호, 공공 API 키, `LLM_API_KEY`)는 **GitHub에 두지 않고 EC2에만 배치**한다. `.gitignore`에 `.env`가 포함되어 있다.

### 5.5 EC2 서버 사전 준비

현행 단일 EC2 기준의 검증된 절차(패키지 설치, Nginx, systemd, cron)는 **`docs/10-implementation-guide.md` §1.3·§2·§11**을 사용한다. 배포 산출물은 저장소의 `deploy/` 에 있다:

| 파일 | 용도 |
|---|---|
| `deploy/c-maker.nginx.conf` | Nginx 리버스 프록시 (`/` → :8080, `/api/` → :8000) |
| `deploy/c-maker-api.service` | FastAPI(Uvicorn) systemd 유닛 |
| `deploy/c-maker-frontend.service` | `serve -s frontend/dist` systemd 유닛 |
| `deploy/c-maker.cron` | `run_daily.py`, `run_monthly.py`, `geocode_job.py` 등록 |

확장 구성(EC2 2대)으로 갈 때는 Frontend EC2에서 `serve` 대신 Nginx 정적 서빙으로 바꾸고, `/api/` 프록시 대상을 Backend EC2의 사설 IP로 지정한다.

---

## 6. 공공 API 호출 — 2가지 케이스 비교 분석

### 6.1 Case A: Frontend에서 직접 호출

```
┌─ 브라우저 ────────────────────────────────────────────┐
│                                                        │
│  React App                                             │
│   └─ usePublicData()                                   │
│       └─ fetch("https://apis.data.go.kr/...            │
│               ?serviceKey=VITE_PUBLIC_API_KEY")         │
│                │                                       │
└────────────────┼───────────────────────────────────────┘
                 │
                 │ HTTPS (브라우저 → 공공 API 서버 직접)
                 │ ⚠️ CORS 정책 적용
                 │ ⚠️ API Key가 브라우저에 노출
                 ▼
        ┌─ 공공 API 서버 ─┐
        │  data.go.kr      │
        └──────────────────┘
```

### 6.2 Case B: Backend를 경유하여 호출

```
┌─ 브라우저 ──────┐     ┌─ EC2: Backend ────────────────┐     ┌─ 공공 API ──┐
│                  │     │                                │     │              │
│  React App       │     │  FastAPI                       │     │  data.go.kr  │
│   └─ fetch(      │────→│   └─ Router → Service → Client │────→│              │
│     "/api/public │     │       │                        │     │              │
│      /tourist")  │     │       ├─ 캐시 확인              │     └──────────────┘
│                  │     │       ├─ API Key 서버 보관       │
│  ※ 공공 API     │     │       └─ 데이터 정제 + 캐싱      │
│    URL 모름      │◄────│                                │
│  ※ API Key 모름  │     │  ※ 서버간 통신: CORS 없음       │
│                  │     │                                │
└──────────────────┘     └────────────────────────────────┘
```

### 6.3 상세 비교표

| 비교 항목 | Case A: Frontend 직접 호출 | Case B: Backend 경유 호출 |
|----------|--------------------------|-------------------------|
| **CORS** | ❌ 차단 가능. 공공 API마다 CORS 지원 여부가 다르며 대부분 불안정. Nginx 프록시 우회 시 결국 서버 경유와 동일 | ✅ 서버 간 통신이므로 CORS 이슈 없음 |
| **API Key 보안** | ❌ `VITE_` 접두사 환경변수는 빌드 시 코드에 삽입되어 브라우저 Network 탭에서 누구나 확인 가능 | ✅ `.env`에 저장, 서버 프로세스만 접근. 브라우저에 일체 노출 없음 |
| **호출 한도 관리** | ❌ 사용자 100명 동시 접속 시 100건 호출 발생. 일일 한도 빠르게 소진 | ✅ 서버 캐시(30분 TTL)로 동일 요청은 1번만 호출. 사용자 100명 → 공공 API 1회 |
| **데이터 가공** | △ 프론트엔드에서 XML→JSON 변환, 필드 추출 등 처리. 브라우저 부하 증가 | ✅ 서버에서 정제 후 필요한 필드만 프론트에 전달 |
| **장애 대응** | ❌ 공공 API 장애가 사용자 화면에 직접 영향. 대체 수단 없음 | ✅ 전일 스냅샷 폴백(RULE-SENSE-04) + 재시도 로직 구현 가능 |
| **로깅·모니터링** | ❌ 브라우저에서의 호출은 서버 로그에 남지 않음 | ✅ 호출 횟수, 응답시간, 에러율 등 서버 로그에 기록. 모니터링 대시보드 구성 가능 |
| **캐싱 효율** | △ 브라우저 메모리 캐시(TanStack Query)만 가능. 사용자별 독립 캐시 | ✅ 2중 캐시 구조 (브라우저 + 서버). 서버 캐시는 모든 사용자가 공유 |
| **개발 복잡도** | ✅ 단순. 프론트엔드에 API 클라이언트만 추가 | △ 백엔드 Router → Service → Client 3개 레이어 추가 필요 |
| **서버 비용** | ✅ 추가 서버 비용 없음 | △ Backend에 추가 부하. 이미 배치용으로 존재하므로 한계적 추가 비용 |
| **LLM 연계** | ❌ 프론트에서 수집한 공공 데이터를 LLM 입력과 결합하려면 결국 백엔드로 전달해야 함. `LLM_API_KEY`를 브라우저에 노출할 수도 없다 | ✅ 서버에서 공공 데이터 + DB 데이터 + LLM 결과를 조합. OPS-06(briefing 모듈 단독 호출) 격리 원칙 유지 |
| **감사 추적** | ❌ REQ-15(감사 추적 로그) 요건 충족 불가 | ✅ 모든 데이터 흐름이 서버를 경유하므로 완전한 감사 추적 가능 |

### 6.4 C-MAKER 프로젝트에 대한 결론

**Case B (Backend 경유)를 권장합니다.** 이유:

1. **보안 요건**: 금융권 시스템으로 API Key 노출은 허용 불가 (PRD 7장 컴플라이언스)
2. **감사 추적**: REQ-15에서 모든 데이터 흐름의 감사 추적을 요구
3. **기존 아키텍처와 일관성**: PRD 5장 아키텍처에서 이미 배치 파이프라인이 공공 API를 서버에서 수집하는 구조
4. **호출 한도**: 국세청 API (1일 100만건), 인허가 데이터 등 한도 관리가 중요
5. **SLA 충족**: 07:30 SLA를 위한 폴백 전략은 서버 스냅샷이 필수
6. **LLM 연계**: 브리프 생성 시 공공 데이터와 LLM 결과를 서버에서 결합하고, `LLM_API_KEY`를 서버에만 둔다

> **Case A는 PoC·프로토타이핑 단계에서만 유효합니다.** 운영 서비스 배포 시에는 반드시 Case B 구조를 사용해야 합니다.

### 6.5 Case A가 유효한 예외 상황

| 상황 | 설명 |
|------|------|
| 초기 PoC / 데모 | 백엔드 완성 전 화면 프로토타입에서 실제 데이터를 빠르게 보여줘야 할 때 |
| 개발 환경 로컬 테스트 | Vite proxy 설정으로 CORS 우회해 API 동작 확인 |
| API Key 노출 무관한 무료 API | 호출 한도가 넉넉하고 보안 요건이 없는 테스트용 API |

---

## 7. 배포를 위한 필수 작업 목록

### 7.1 인프라 구성 작업

| # | 작업 | 상세 | 현행 단일 EC2 | 확장 구성 |
|---|------|------|---|---|
| 1 | **VPC 생성** | CIDR: 10.0.0.0/16, Public/Private Subnet × 2 AZ | 기본 VPC 사용 | 필수 |
| 2 | **EC2 Frontend 인스턴스** | Nginx 정적 서빙 | 불필요 (단일 EC2에 serve) | 필수 |
| 3 | **EC2 Backend 인스턴스** | Python 3.14, Nginx, 배치용 메모리 | ✅ 구성 완료 | 필수 |
| 4 | **RDS PostgreSQL 18** | Private Subnet, Multi-AZ (운영), 자동 백업 | 불필요 (localhost PG 18.6) | 권장 |
| 5 | **Security Group 설정** | §3.3 / 현행은 구현가이드 §1.2 | ✅ 적용 | 필수 |
| 6 | ~~**IAM Role (EC2 → Bedrock)**~~ | **제거됨** — Bedrock 직접 호출 없음(§1.2) | 불필요 | 불필요 |
| 7 | ~~**AWS Bedrock 설정**~~ | **제거됨** — AI Agent·Knowledge Base 구성 불필요(§1.2) | 불필요 | 불필요 |
| 8 | **LiteLLM Gateway 연결 확인** | DNS + 아웃바운드 443 + Virtual Key | ✅ **EC2 검증 완료** (브리프 5/5 `LLM`, 2026-09-30) | 필수 |
| 9 | **SSL 인증서** | ACM 또는 Let's Encrypt, HTTPS 적용 | ❌ 미적용 (현재 80만 사용) | 필수 |
| 10 | **도메인 설정** | Route 53 또는 기존 DNS에 A/CNAME 레코드 | 미설정 | 권장 |
| 11 | **CloudWatch 설정** | EC2/RDS 모니터링, 알람 구성 | 미설정 | 권장 |

### 7.2 애플리케이션 준비 작업

| # | 작업 | 상세 | 우선순위 |
|---|------|------|----------|
| 1 | **환경변수 파일 구성** | `.env` — DB 접속정보, 공공 API 키, `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`. 템플릿은 `.env.example` | 필수 |
| 2 | **`APP_ENV=prod` 확인** | dev로 두면 `/api/docs`가 노출된다 | 필수 |
| 3 | **Frontend 빌드 환경변수** | `VITE_API_BASE_URL=/api` | 필수 |
| 4 | **DB 스키마 마이그레이션** | `database/schema.sql` 실행 (`cmaker` 스키마 생성), 트리거 동작 확인 | 필수 |
| 5 | **BRANCH/USER 초기 데이터** | 운영자가 psql로 직접 INSERT (REQ-01) | 필수 |
| 6 | **공공 API 키 발급** | data.go.kr 서비스 키 + ECOS·오피넷·VWorld 별도 포털 | 필수 |
| 7 | ~~**Bedrock AI Agent 구성**~~ | **제거됨** — Action Group·KB 색인 불필요(§1.2) | 불필요 |
| 8 | **LLM 게이트웨이 설정 검증** | `LLM_DISABLE_THINKING=true`, `LLM_TIMEOUT_SECONDS=10` (구현가이드 §8.2) | ✅ 완료 |
| 9 | **Nginx 설정 파일** | `deploy/c-maker.nginx.conf` 적용 | 필수 |
| 10 | **systemd 서비스 등록** | `deploy/c-maker-api.service`, `c-maker-frontend.service` | 필수 |
| 11 | **cron 등록** | `deploy/c-maker.cron` — 일간/월간/지오코딩 | 필수 |
| 12 | **로그 수집 설정** | `LOG_DIR` 지정 (예: `/var/log/c-maker`) + 로테이션 | 권장 |

### 7.3 GitHub CI/CD 구성 작업

| # | 작업 | 상세 | 우선순위 |
|---|------|------|----------|
| 1 | **GitHub Repository** | 모노레포 (`frontend/` + `backend/`) | ✅ 완료 |
| 2 | **GitHub Secrets 등록** | SSH Key, EC2 Host | 필수 |
| 3 | **GitHub Actions 워크플로우** | Lint → Test → Build → Deploy 파이프라인 | 필수 |
| 4 | **Branch Protection Rules** | main 브랜치 보호, PR 리뷰 필수 | 권장 |
| 5 | **.gitignore 정비** | `.env`, `node_modules/`, `__pycache__/`, `dist/`, `data/` | ✅ 완료 |
| 6 | **PR 템플릿** | 변경사항 체크리스트, 테스트 결과 기록 | 권장 |

### 7.4 보안 검토 필요 사항 (PRD 6장·10장 연계)

| # | 사항 | 상태 | 담당 |
|---|------|------|------|
| 1 | ~~AWS Bedrock 리전 선택~~ | ✅ **해소** — EC2가 Bedrock을 직접 부르지 않는다. 리전 선택은 게이트웨이 운영 주체의 소관 | — |
| 2 | **LiteLLM Gateway 구간 PrivateLink / 전용망 적용 여부** | 보안팀 확인 필요 (검토 대상이 Bedrock → 게이트웨이로 변경) | 보안·IT |
| 3 | **게이트웨이로의 데이터 반출 범위 승인** | 보안팀 확인 필요. 현재 전송 항목은 지점명·상호·업종·공개 데이터 기반 사실 문장 (개인정보 없음, RULE-SEC-01) | 보안 |
| 4 | `LLM_API_KEY`(Virtual Key) 관리 | 서버 `.env`에만 보관 중. Secrets Manager 이관 검토 | 개발·보안 |
| 5 | USER 비밀번호 평문 저장 → 해싱 전환 검토 | 검토 필요 | 개발·보안 |
| 6 | 공공 API 키 관리 방안 | AWS Secrets Manager 권장 | 개발 |
| 7 | HTTPS 미적용 (현재 80 포트) | 로그인 자격증명이 평문 전송된다. 운영 전 필수 조치 | 개발·보안 |

---

## 8. 비용 추정 및 권장 사양

### 8.1 인스턴스 권장 사양

**현행 단일 EC2 구성**

| 리소스 | 사양 | 월 추정비용 (서울 리전) | 비고 |
|--------|------|----------------------|------|
| **EC2 (통합)** | t3.medium (2 vCPU, 4 GB) | ~$38 | Nginx + serve + FastAPI + PostgreSQL + 배치 |
| **EBS** | 50 GB gp3 | ~$5 | DB + 배치 스냅샷 |
| **데이터 전송** | — | ~$5 | |
| **LiteLLM Gateway** | 사내 게이트웨이 | **별도 확인 필요** | AWS 청구에 포함되지 않음. 사용료 청구 주체·한도를 게이트웨이 관리자에게 확인 |
| **합계** | — | **~$48/월** | |

**확장 구성 (EC2 분리 + RDS)**

| 리소스 | 사양 | 월 추정비용 (서울 리전) | 비고 |
|--------|------|----------------------|------|
| **EC2 Frontend** | t3.small (2 vCPU, 2 GB) | ~$19 | 정적 파일 서빙, 부하 낮음 |
| **EC2 Backend** | t3.medium (2 vCPU, 4 GB) | ~$38 | API + 배치 프로세스 동시 운영 |
| **RDS PostgreSQL** | db.t3.medium (2 vCPU, 4 GB) | ~$70 | 20 GB gp3 스토리지 포함 |
| **EBS (Frontend)** | 20 GB gp3 | ~$2 | |
| **EBS (Backend)** | 50 GB gp3 | ~$5 | 배치 스냅샷 임시 저장 |
| **데이터 전송** | — | ~$10 | 월 100 GB 기준 |
| **LiteLLM Gateway** | 사내 게이트웨이 | 별도 확인 필요 | 상동 |
| **합계 (AWS 항목)** | — | **~$144/월** | |

> **v1.0.0과의 차이** — v1.0.0은 `AWS Bedrock 사용량 기반 ~$50~200/월`을 AWS 비용에 포함했다. 실제로는 사내 LiteLLM Gateway를 경유하므로 **이 프로젝트의 AWS 청구서에 Bedrock 항목이 잡히지 않는다.** 대신 게이트웨이 사용료·호출 한도의 정산 주체를 확인해야 한다.

### 8.2 확장 시 고려사항

| 단계 | 추가 고려 | 이유 |
|------|----------|------|
| MVP | 07:30 배치 전체 실행 시간 측정 | 브리프 1건은 EC2 실측 3.77초로 UC-07 충족(§4.2). 전체 SLA는 지점 수 확정 후 측정 필요. 초과 시 `claude-haiku-4-5` 전환 검토 |
| Phase 2 | Backend EC2 → t3.large (8 GB) | 운영 예측(REQ-10), 상품 안내(REQ-11) 배치 추가 |
| Phase 2 | RAG 파이프라인 자체 구축 | Bedrock Knowledge Base를 쓰지 않으므로 REQ-11은 직접 구현 필요. 게이트웨이의 `amazon.titan-embed-text-v2:0`(임베딩, 8192 토큰) 활용 가능 |
| Phase 2 | Redis (ElastiCache) 추가 | 공공 API 캐싱 전용, 서버 메모리 절약 |
| Phase 3 | ALB + Auto Scaling Group | 전행 확산 시 동시 접속자 증가 대비 |
| Phase 3 | RDS Multi-AZ 활성화 | 99.5% 가용성 SLA 충족 |
| Phase 3 | CloudFront CDN | Frontend 정적 파일 글로벌 캐싱 |

---

## 부록 A. 전체 아키텍처 한눈에 보기 (확장 구성)

```
┌──────────────┐         ┌───────────────┐        ┌─────────────────────────────────────┐
│  WorkSpaces  │── git ──│    GitHub      │── CI ──│          AWS Cloud (서울 리전)         │
│  (개발 환경)   │  push   │  (소스 관리)    │  /CD   │                                     │
└──────────────┘         └───────────────┘        │  ┌─────────┐     ┌──────────────┐   │
                                                   │  │Frontend │────▶│  Backend      │   │
                              ┌─────────────┐      │  │ EC2     │ API │  EC2          │   │
                              │ 사용자       │      │  │ (Nginx  │     │  (FastAPI     │   │
                              │ (브라우저)    │─────▶│  │  +React)│     │   +Batch)     │   │
                              └─────────────┘      │  └─────────┘     └──┬───────┬────┘   │
                                                   │                     │       │         │
                                                   │                     ▼       │         │
                                                   │      ┌─────────────────┐    │         │
                                                   │      │ RDS PostgreSQL  │    │         │
                                                   │      │ (Private Subnet)│    │         │
                                                   │      └─────────────────┘    │         │
                                                   └─────────────────────────────┼─────────┘
                                                                                 │ HTTPS 443
                                              ┌──────────────────────────────────┴───┐
                                              ▼                                       ▼
                                  ┌────────────────────────┐          ┌────────────────────┐
                                  │ 사내 LiteLLM Gateway    │          │  공공 API           │
                                  │ /v1/chat/completions   │          │  (data.go.kr 등 8종)│
                                  │  └─ 백엔드: Bedrock     │          └────────────────────┘
                                  └────────────────────────┘
```

---

## 부록 B. 배포 체크리스트

배포 전 최종 확인 사항:

**인프라**
- [ ] VPC, Subnet, Internet Gateway 생성 완료 (확장 구성 시)
- [ ] EC2 인스턴스 실행 중 (현행: 단일 / 확장: Frontend + Backend)
- [ ] PostgreSQL 18 실행 중 (현행: localhost / 확장: RDS)
- [ ] Security Group 규칙 적용 완료 — **아웃바운드 443에 LiteLLM Gateway 도달 확인**
- [ ] SSL 인증서 발급 및 Nginx HTTPS 설정 (**현재 미적용 — §7.4-7**)

**애플리케이션**
- [ ] Frontend: `npm run build` 성공, `c-maker-frontend` systemd 등록
- [ ] Backend: `backend/requirements.txt` 설치, `c-maker-api` systemd 등록
- [ ] `.env` 배치 — DB 접속정보, 공공 API 키, `LLM_BASE_URL`(`.../v1`)·`LLM_API_KEY`·`LLM_MODEL`
- [ ] `APP_ENV=prod` 확인 (`/api/docs` 비노출)
- [ ] `FRONTEND_ORIGIN` 지정 — CORS 와일드카드 금지 (OPS-07)
- [ ] DB: `schema.sql` 실행, BRANCH/USER 초기 데이터 INSERT
- [ ] Cron: `deploy/c-maker.cron` 등록 (일간/월간/지오코딩)
- [ ] 공공 API 키: data.go.kr 8종 + ECOS·오피넷·VWorld 발급 및 `.env` 등록

**LLM 연동**
- [ ] `GET /v1/models` 로 게이트웨이 도달 및 모델 가용 확인
- [ ] 브리프 1건 실호출 성공 — `generation_status="LLM"` 확인 (TEMPLATE 폴백이면 실패)
- [ ] `LLM_DISABLE_THINKING=true` 적용 확인 (미적용 시 빈 응답)
- [ ] ~~Bedrock AI Agent + Knowledge Base 구성~~ — **불필요**
- [ ] ~~IAM Role: EC2 → Bedrock 접근 권한~~ — **불필요**

**운영**
- [ ] CI/CD: GitHub Actions 워크플로우 테스트 배포 성공
- [ ] 모니터링: CloudWatch 알람 구성 (CPU, 메모리, 디스크)
- [ ] 07:30 SLA 테스트: `run_daily.py` 수동 실행 → 완료 시간 확인 (**LLM 지연 7.4초/건 반영, §4.2**)

---

*본 보고서는 C-MAKER 프로젝트의 `agents/*.md` 에이전트 정의, `docs/*` 아키텍처 문서, `backend/`·`frontend/`·`deploy/` 소스 구성을 기반으로 작성되었습니다. LLM 연동 관련 수치는 2026-09-30 LiteLLM Gateway 실호출 결과입니다.*
