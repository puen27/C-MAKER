# C-MAKER 구현 가이드

- **버전**: v2.2.0
- **작성일**: 2026-09-29 (v2.2.0 현행화: 2026-09-29)
- **목적**: EC2 단일 인스턴스에 프론트엔드·백엔드·DB를 구성하고, MVP 기능을 구현하기 위한 종합 구현 계획서
- **작성 방법**: grill-me 방식으로 39개 설계 결정을 확정한 뒤 작성
- **v2.1.0 변경**: EC2 서버 현행 구성(Tomcat→serve 전환 완료, Node.js v24/nvm, Python 3.14.4, PostgreSQL 18.6) 반영
- **v2.2.0 변경**: DB를 기존 `myapp_db`/`myapp_user` 사용으로 확정. `cmaker`/`cmaker_app` 신규 생성 관련 내용 전면 삭제

---

## 참조 문서

| 문서 | 버전 | 역할 |
|---|---|---|
| `1-domain-definition.md` | v1.4.0 | REQ, VAL, RULE, UC, 엔티티 정의 |
| `2-prd.md` | v1.4.0 | 비즈니스 목표, 기술 스택, 비기능 요건 |
| `3-user-scenario.md` | v1.3.0 | SC-01~09 사용 흐름 |
| `4-project-principle.md` | v1.5.0 | 디렉토리 구조, 레이어 원칙, 네이밍 |
| `5-arch-diagram.md` | v1.3.1 | 시스템 구성도, 배치 파이프라인 |
| `6-erd.md` | v1.4.0 | DB 스키마, 제약사항 |
| `7-execution-plan.md` | v1.4.0 | 스프린트별 작업 항목 |
| `8-wireframe.md` | v1.3.0 | 화면 레이아웃 |
| `9-style-guide.md` | v1.3.0 | 디자인 토큰, 컴포넌트 스타일 |
| `public data sources.md` | v1.1.0 | 공공데이터 API 신청 현황, 인증키 관리 |

---

## 1. 인프라 구성 — EC2 단일 인스턴스

### 1.1 네트워크 포트 구성

> **현행 확인 (2026-09-29)**: 기존에 8080 포트를 점유하던 Tomcat 11.0.26은 `systemctl disable` 처리 완료. serve가 8080을 사용하는 아래 구성이 현재 서버와 일치한다.

```
┌─ EC2 (Ubuntu 26.04.1 LTS) ────────────────────────────────────────┐
│                                                                     │
│  ┌─ Nginx (:80) ─────────────────────────────────────────────────┐  │
│  │  리버스 프록시                                                  │  │
│  │  /           → localhost:8080  (프론트엔드, serve)              │  │
│  │  /api/*      → localhost:8000  (백엔드, FastAPI)                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ serve (:8080) ───────────────────────────────────────────────┐  │
│  │  React SPA 정적 파일 서빙 (frontend/dist/)                     │  │
│  │  SPA fallback: serve -s 옵션                                   │  │
│  │  systemd 서비스로 관리                                          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ FastAPI + Uvicorn (:8000) ───────────────────────────────────┐  │
│  │  백엔드 API 서버                                                │  │
│  │  → PostgreSQL (localhost:5432)                                  │  │
│  │  → 공공데이터 API (HTTPS 아웃바운드)                              │  │
│  │  → LiteLLM Gateway (HTTPS 아웃바운드)                            │  │
│  │  systemd 서비스로 관리                                          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ PostgreSQL (:5432) ──────────────────────────────────────────┐  │
│  │  localhost 전용, scram-sha-256 인증                             │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ 배치 프로세스 (cron) ────────────────────────────────────────┐  │
│  │  run_daily.py   — 매일 06:00 (07:30 SLA)                      │  │
│  │  run_monthly.py — 매월 1일 01:00                                │  │
│  │  geocode_job.py — 10분 주기                                     │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Security Group

| 방향 | 포트 | 소스/대상 | 용도 |
|---|---|---|---|
| 인바운드 | 80 | 0.0.0.0/0 | 웹 접속 (Nginx) |
| 인바운드 | 22 | 관리 IP | SSH |
| 아웃바운드 | 443 | 0.0.0.0/0 | 공공 API + LiteLLM Gateway |
| 내부 | 5432 | localhost | PostgreSQL |
| 내부 | 8000 | localhost | FastAPI |
| 내부 | 8080 | localhost | serve |

### 1.3 EC2 초기 설정

> **현행 확인 (2026-09-29)**: 아래 패키지는 이미 설치 완료된 상태.
> Python 3.14.4, Node.js v24.21.0 (nvm), npm 11.19.0, PostgreSQL 18.6, Nginx 1.28.3, serve 14.2.6

```bash
# Ubuntu 26.04.1 LTS 기준
# ── 이미 설치된 패키지는 건너뛴다 ──

# 1) 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 2) Python (Ubuntu 26.04 기본 제공 3.14.x)
sudo apt install python3 python3-pip python3-venv -y

# 3) PostgreSQL
sudo apt install postgresql postgresql-contrib -y
sudo systemctl enable --now postgresql

# 4) Nginx
sudo apt install nginx -y
sudo systemctl enable --now nginx

# 5) Node.js — nvm으로 관리 (현행 v24.21.0)
#    nodesource 대신 nvm 사용. 이미 설치되어 있으면 생략.
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 24    # 현행 서버 기준. 20 LTS도 호환됨.

# 6) serve (전역 설치)
npm install -g serve

# 7) Tomcat이 설치되어 있다면 비활성화 (8080 포트 충돌 방지)
sudo systemctl stop tomcat 2>/dev/null
sudo systemctl disable tomcat 2>/dev/null

# 8) 프로젝트 클론
cd /home/ubuntu
git clone <repository-url> c-maker
cd c-maker

# 9) Python 가상환경 (프로젝트 루트)
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

---

## 2. Nginx 설정

> **현행 확인 (2026-09-29)**: 기존 `/etc/nginx/sites-available/myapp` (Tomcat + FastAPI 프록시)은 `myapp.bak`으로 백업 후 제거 완료. 아래 `c-maker` 설정이 현재 서버에 적용되어 있다.

```nginx
# /etc/nginx/sites-available/c-maker

server {
    listen 80;
    server_name _;

    # API → FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # 프론트엔드 → serve
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 보안 헤더
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
}
```

```bash
# 기존 myapp 설정 백업 (이미 완료된 경우 생략)
sudo cp /etc/nginx/sites-available/myapp /etc/nginx/sites-available/myapp.bak 2>/dev/null
sudo rm -f /etc/nginx/sites-enabled/myapp

sudo ln -sf /etc/nginx/sites-available/c-maker /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 3. 환경변수

### 3.1 `.env` (저장소 루트, .gitignore에 포함)

```bash
# ── DB ──
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp_db
DB_USER=myapp_user
DB_PASSWORD=<myapp_user-password>

# ── JWT ──
JWT_SECRET=<random-256bit-secret>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# ── 공공데이터 API ──
DATA_GO_KR_SERVICE_KEY=<디코딩키>
ECOS_API_KEY=
OPINET_API_KEY=

# ── LLM (LiteLLM Gateway, OpenAI-Compatible) ──
# base_url은 /v1 까지 포함한다 (openai 패키지가 /chat/completions를 붙인다)
LLM_BASE_URL=https://frontier-llmgw.aipocnhbank.com/v1
LLM_API_KEY=<LiteLLM Virtual Key, sk-...>
LLM_MODEL=claude-opus-5
LLM_TIMEOUT_SECONDS=10
LLM_DISABLE_THINKING=true

# ── 배치 ──
BATCH_COOLDOWN_MINUTES=30

# ── 서버 ──
FRONTEND_ORIGIN=http://localhost
```

### 3.2 `frontend/.env`

```bash
VITE_API_BASE_URL=/api
```

### 3.3 `.env.example` (커밋 대상, 키 없이 변수명만)

```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp_db
DB_USER=
DB_PASSWORD=
JWT_SECRET=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
DATA_GO_KR_SERVICE_KEY=
ECOS_API_KEY=
OPINET_API_KEY=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=claude-opus-5
LLM_TIMEOUT_SECONDS=10
LLM_DISABLE_THINKING=true
BATCH_COOLDOWN_MINUTES=30
FRONTEND_ORIGIN=http://localhost
```

---

## 4. PostgreSQL 초기화

> **현행 확인 (2026-09-29)**: 서버에 PostgreSQL 18.6 가동 중. 기존에 생성된 **`myapp_db` (owner: `myapp_user`)를 C-MAKER 운영 DB로 사용한다.** 신규 DB/유저는 생성하지 않는다.

```bash
# DB/유저 생성 단계 없음 — 기존 myapp_db / myapp_user 사용

# pg_hba.conf — scram-sha-256 인증 확인
# local   all   myapp_user   scram-sha-256
# ※ peer 인증만 설정되어 있으면 psql -U myapp_user 접속 시 실패하므로 확인 필요
sudo grep -nE '^(local|host)' /etc/postgresql/*/main/pg_hba.conf

# 접속 확인
psql -U myapp_user -d myapp_db -c "SELECT current_database(), current_user;"

# 스키마 적용
cd /home/ubuntu/c-maker
psql -U myapp_user -d myapp_db -f backend/database/schema.sql

# 테이블 생성 확인
psql -U myapp_user -d myapp_db -c "\dt"
```

> **주의**: `myapp_db`에 기존 테이블이 남아 있다면 C-MAKER 스키마와 이름이 충돌할 수 있다. 스키마 적용 전 `\dt`로 기존 테이블 목록을 확인한다.

---

## 5. 백엔드 구조

### 5.1 디렉토리 (`4-project-principle.md` §6 기준)

```
backend/
├── batch/
│   ├── connectors/                 # 소스별 원본 수집
│   │   ├── sbiz_connector.py        # 소진공 상가(상권)정보 (S-1, REQ-16)
│   │   ├── nts_connector.py         # 국세청 사업자등록상태 (S-8, REQ-02)
│   │   ├── permit_connector.py      # 행안부 지방행정 인허가 (F-2/N-1)
│   │   ├── kma_connector.py         # 기상청 특보 (S-2)
│   │   ├── holiday_connector.py     # 천문연 특일정보 (S-3)
│   │   ├── subway_connector.py      # 지하철 승하차
│   │   ├── ecos_connector.py        # 한국은행 ECOS
│   │   ├── opinet_connector.py      # 오피넷 유가정보
│   │   └── disaster_msg_connector.py # 긴급재난문자
│   ├── population/                 # 사업체 모집단 적재 (REQ-16)
│   │   └── business_loader.py
│   ├── normalizers/
│   │   └── signal_normalizer.py
│   ├── sensing/                    # 이벤트 승격 (도메인 정의서 5.1절)
│   │   ├── threshold_engine.py
│   │   └── event_promoter.py
│   ├── targeting/                  # 배제·스코어링·탐색슬롯
│   │   ├── exclusion.py
│   │   ├── scorer.py
│   │   ├── reason_tier.py
│   │   └── exploration.py
│   ├── briefing/                   # LLM 브리프 생성
│   │   ├── llm_client.py            # openai 패키지, base_url=LiteLLM Gateway
│   │   ├── brief_generator.py
│   │   └── citation_guard.py        # 프롬프트 지시 + 출처 태그 포맷 강제
│   ├── geocoding/
│   │   └── geocode_job.py
│   ├── run_daily.py
│   ├── run_weekly.py                # Phase 2
│   ├── run_monthly.py
│   └── run_quarterly.py             # Phase 2
├── api/
│   ├── routers/
│   │   ├── auth.router.py
│   │   ├── recommendations.router.py
│   │   ├── tags.router.py
│   │   ├── thresholds.router.py
│   │   └── batch.router.py
│   ├── services/
│   │   ├── auth.service.py
│   │   ├── recommendation.service.py
│   │   ├── tag.service.py
│   │   ├── threshold.service.py
│   │   └── batch.service.py
│   ├── repositories/
│   │   ├── user.repository.py
│   │   ├── recommendation.repository.py
│   │   ├── tag.repository.py
│   │   ├── threshold.repository.py
│   │   └── batch_run.repository.py
│   ├── middlewares/
│   │   ├── auth.middleware.py
│   │   └── error.middleware.py
│   └── app.py
├── common/
│   ├── config.py
│   ├── geo.py                      # EPSG:5174 → WGS84 (VAL-11)
│   ├── db/
│   │   └── pool.py                 # psycopg AsyncConnectionPool
│   ├── schemas/                    # Pydantic 모델
│   │   ├── auth.py
│   │   ├── signal.py
│   │   ├── event.py
│   │   ├── recommendation.py
│   │   ├── brief.py
│   │   ├── business.py
│   │   └── batch_run.py
│   └── snapshot_store.py
├── database/
│   └── schema.sql
├── requirements.txt
└── .env.example
```

### 5.2 의존성 (`requirements.txt`)

> **참고**: 현행 서버 Python 3.14.4 기준. `python-jose`는 Python 3.13+ 에서 빌드 문제가 보고된 사례가 있으므로, 설치 실패 시 `PyJWT`로 대체를 검토한다.

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
psycopg[binary]==3.2.*
psycopg_pool==3.2.*
pydantic==2.10.*
pydantic-settings==2.6.*
python-jose[cryptography]==3.3.*
requests==2.32.*
httpx==0.28.*
openai==1.82.*
pyproj==3.7.*
python-dotenv==1.0.*
```

| 패키지 | 용도 |
|---|---|
| `fastapi` + `uvicorn` | API 서버 |
| `psycopg` + `psycopg_pool` | PostgreSQL 접속 (ORM 없음, 직접 SQL) |
| `pydantic` | 데이터 검증, 스키마 계약 (PRIN-05) |
| `python-jose` | JWT 발급/검증 |
| `requests` | 배치에서 공공 API 동기 호출 |
| `httpx` | API 서버에서 비동기 HTTP 호출 |
| `openai` | LiteLLM Gateway 호출 (`base_url` 변경) |
| `pyproj` | EPSG:5174 → WGS84 좌표 변환 (VAL-11) |

### 5.3 레이어 원칙

```
Router (라우팅만) → Service (도메인 규칙) → Repository (SQL 실행)
```

- 레이어 건너뛰기 금지 (DEP-03): Router가 Repository를 직접 호출하지 않음
- 같은 레이어 순환 참조 금지 (DEP-02)
- 인증/권한 검증은 미들웨어에서 공통 처리 (OPS-03)

---

## 6. API 엔드포인트

### 6.1 MVP 엔드포인트

| 메서드 | 경로 | UC | 역할 제한 | 설명 |
|---|---|---|---|---|
| `POST` | `/api/auth/login` | — | 전체 | 로그인, JWT 발급 |
| `GET` | `/api/recommendations` | UC-06 | RM, 지점장 | 오늘의 접촉 TOP 20 (소속 지점만) |
| `GET` | `/api/recommendations/{id}/brief` | UC-07 | RM, 지점장 | 상담 브리프 상세 |
| `POST` | `/api/recommendations/{id}/tag` | UC-09 | RM | 태깅 저장 (VAL-06) |
| `GET` | `/api/recommendations/export` | UC-08 | RM | CRM 파일 다운로드 (CSV/XLSX) |
| `GET` | `/api/thresholds` | UC-15 | HQ_MARKETING | 임계치 목록 |
| `PUT` | `/api/thresholds/{id}` | UC-15 | HQ_MARKETING | 임계치 변경 (VAL-05, REQ-15 이력) |
| `GET` | `/api/thresholds/{id}/history` | UC-15 | HQ_MARKETING | 변경 이력 |
| `POST` | `/api/batch/trigger` | UC-18 | 지점장, HQ_MARKETING | 수동 재실행 (RULE-SENSE-06, VAL-12) |
| `GET` | `/api/batch/status` | UC-18 | 지점장, HQ_MARKETING | 배치 상태 조회 |

### 6.2 공통 에러 응답 (PRIN-06)

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "..." } }
```

### 6.3 주요 요청/응답

**로그인**

```
POST /api/auth/login
Request:  { "username": "...", "password": "..." }
Response: { "token": "eyJ...", "user": { "id", "name", "role", "branchId", "branchName" } }
```

**추천 목록**

```
GET /api/recommendations?date=2026-08-26
Response: [ { "id", "rank", "businessName", "industry", "score",
              "reasonSummary", "reasonSourceTag", "tagStatus",
              "rejectedReason", "carriedOverFromYesterday" } ]
```

**태깅**

```
POST /api/recommendations/{id}/tag
Request: { "tagStatus": "REJECTED", "rejectedReason": "NOT_TARGET" }
```

---

## 7. DB 스키마

`database/schema.sql` 단일 파일 관리 (OPS-09). `6-erd.md` v1.4.0 기준.

### 7.1 테이블 생성 순서

FK 참조 순서에 맞춰 다음 순서로 생성한다.

```
1. branch
2. branch_history          → branch
3. user                    → branch
4. data_source_snapshot
5. event                   → branch
6. business
7. signal                  → data_source_snapshot, branch, business, event
8. recommendation          → branch, business
9. recommendation_event    → recommendation, event
10. brief                  → recommendation
11. tag_feedback           → recommendation, user
12. signal_weight
13. threshold_config       → user
14. batch_run              → user
```

### 7.2 트리거 (CONST-19)

BRANCH INSERT/UPDATE 시:
- UPDATE인 경우 옛 값을 `branch_history`로 이동
- `effective_from`을 다음 날 07:30으로 자동 설정

### 7.3 인덱스

```
idx_recommendation_branch_date  ON recommendation(branch_id, recommended_on)
idx_signal_branch_date          ON signal(branch_id, as_of_date)
idx_event_branch_date           ON event(branch_id, occurred_on)
idx_business_status             ON business(operating_status)
idx_tag_feedback_recommendation ON tag_feedback(recommendation_id)
idx_batch_run_status            ON batch_run(status)
```

### 7.4 초기 데이터 (psql 직접 입력)

파일럿 지점 온보딩 시 다음 3가지를 투입한다.

| 테이블 | 투입 방법 | 비고 |
|---|---|---|
| BRANCH | psql INSERT | UC-01/02 화면 없음, 운영자 직접 입력 |
| USER | psql INSERT | 계정 생성 화면 없음 |
| THRESHOLD_CONFIG | psql INSERT | 임계치 초기값이 없으면 배치 판정 동작 안 함 |

---

## 8. LLM 연동 (브리프 생성)

> **연동 검증 완료 (2026-09-30)** — 아래 값은 게이트웨이에 실제 호출해 확인한 결과다.

### 8.1 구성

- **Endpoint**: `POST https://frontier-llmgw.aipocnhbank.com/v1/chat/completions`
- **프로토콜**: OpenAI-Compatible API (Chat Completion)
- **라이브러리**: `openai==1.109.1` (`base_url`을 `.../v1` 로 지정)
- **인증**: LiteLLM Virtual Key — `Authorization: Bearer sk-...`
- **모델**: `claude-opus-5`

`GET /v1/models` 로 확인한 제공 모델:

| 모델 ID | mode | max_input | max_output |
|---|---|---|---|
| `claude-opus-5` | chat | 1,000,000 | 128,000 |
| `claude-sonnet-5` | chat | 1,000,000 | 128,000 |
| `claude-opus-4-8` | chat | 1,000,000 | 128,000 |
| `claude-haiku-4-5-20251001-v1:0` | chat | 200,000 | 64,000 |
| `global.anthropic.claude-fable-5-1` | chat | 200,000 | 64,000 |
| `nova-2-lite-v1:0` | — | — | — |
| `amazon.titan-embed-text-v2:0` | embedding | 8,192 | — |
| `stability.stable-image-ultra-v1:1` | image_generation | 77 | — |

> `amazon.titan-embed-text-v2:0`은 REQ-11(상품설명서 RAG, Phase 2) 임베딩에 쓸 수 있다.

### 8.2 게이트웨이 제약 (실측)

| 제약 | 내용 | 대응 |
|---|---|---|
| `temperature` | `claude-opus-5`·`claude-opus-4-8` 모두 `temperature=1` 만 허용. 그 외 값은 HTTP 400 `litellm.UnsupportedParamsError` | `temperature`를 **보내지 않는다**. PRIN-08 재현성은 temperature로 확보 불가 |
| extended thinking | 기본 ON. thinking 토큰이 `max_tokens`를 먼저 소진해 `finish_reason="length"` + `content=""` 반환 | 요청 본문에 `"thinking": {"type": "disabled"}` 전달 (`LLM_DISABLE_THINKING=true`) |
| `reasoning_effort` | `"none"` 을 줘도 thinking이 꺼지지 않는다 | 사용하지 않음 |
| 지연 | **호출 위치에 따라 크게 다르다.** EC2에서 3.24~4.61초 / 개발 PC에서 7.4초 (§8.5) | `LLM_TIMEOUT_SECONDS=10` (EC2 실측 max의 약 2배) |

### 8.3 호출 방식

```
briefing/llm_client.py
  └─ openai.OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=15, max_retries=1)
     └─ client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{system}, {user}],
            max_tokens=BriefingConfig.max_output_tokens,   # 400
            extra_body={"thinking": {"type": "disabled"}},
        )
```

확정된 RECOMMENDATION의 사실 문장만 user 메시지에 넣어 Chat Completion으로 생성한다.
응답은 `{"script": ["문장1", ...]}` JSON으로 받아 `brief_generator.parse_script()`가 파싱한다
(실측: 실제 프롬프트로 216 completion tokens, 유효 JSON 반환 확인).

빈 응답·타임아웃·400은 `LlmUnavailableError`로 올려 `TEMPLATE` 정형 화법으로 대체한다.

### 8.4 EC2 연동 검증 결과 (2026-09-30)

EC2(`ip-10-49-0-19`)에서 `.venv/bin/python`으로 `generate_brief()`를 직접 호출해 검증했다. DB는 사용하지 않았다.

| 항목 | 결과 |
|---|---|
| DNS | `frontier-llmgw.aipocnhbank.com` → `3.39.77.44`, `43.202.16.2` (정상) |
| 아웃바운드 443 | 도달 확인. 프록시 설정 불필요 (`no proxy vars`) |
| 인증 | Virtual Key로 200 응답 |
| `generation_status` | **5건 모두 `LLM`** (TEMPLATE 폴백 없음) |
| `model_version` | `claude-opus-5` |
| citation guard | `validation_errors` 없음 3건, "화법 4문장 → 3문장 절삭" 2건 (정상 동작) |

### 8.5 지연 실측 — 호출 위치에 따라 2배 차이

| 위치 | n | min | median | max | UC-07 5초 초과 |
|---|---|---|---|---|---|
| **EC2 (서울 리전)** | 5 | 3.24초 | 3.77초 | 4.61초 | **0/5** |
| 개발 PC (사내망 → 인터넷) | 1 | — | 7.4초 | — | 초과 |

게이트웨이 IP가 AWS 서울 리전(`3.39.x`, `43.202.x`)이라 EC2에서는 같은 리전 내 통신이 된다.
**UC-07의 "브리프 1건 5초 이내"는 EC2에서 충족된다.** 개발 PC 기준 수치로 SLA를 판단하면 안 된다.

### 8.6 citation guard (RULE-BRIEF-02)

- 프롬프트에 "주어진 데이터 외의 사실을 인용하지 마라" 지시
- 출처 태그 `[소스명·기준일]` 포맷 필수 강제
- 후처리 파싱/검증은 하지 않음

---

## 9. 프론트엔드 연동

### 9.1 현재 구현 상태

| 구분 | 완료 | MVP 추가 필요 |
|---|---|---|
| Pages | LoginPage, DashboardPage, BriefDetailPage | — |
| Components | Layout, Button, StatusBadge, Tabs, TagButtons, RecommendationCard/List, BriefDetail | ManualBatchTrigger |
| API | client.ts, auth/recommendation/brief/tag .api.ts (mock) | mock→apiFetch 교체, batch.api.ts 신규 |
| Queries | useAuth, useRecommendations, useBrief, useTagMutation | useTriggerBatch, useBatchRunStatus |
| Types | auth.ts, recommendation.ts, brief.ts | batchRun.ts, UserRole 보강 |

### 9.2 mock → 실제 API 교체

| 파일 | mock 호출 | 교체 대상 |
|---|---|---|
| `auth.api.ts` | `mockLogin()` | `apiFetch('/auth/login', { method: 'POST', body })` |
| `recommendation.api.ts` | `mockFetchRecommendations()` | `apiFetch('/recommendations?date=...')` |
| `brief.api.ts` | `mockFetchBrief()` | `apiFetch('/recommendations/{id}/brief')` |
| `tag.api.ts` | `mockUpdateTag()` | `apiFetch('/recommendations/{id}/tag', { method: 'POST', body })` |

교체 완료 후 `mockData.ts` 삭제.

### 9.3 신규 작업

- `types/batchRun.ts` — BatchRun 타입 정의
- `api/batch.api.ts` — triggerBatch, fetchBatchStatus
- `queries/useTriggerBatch.ts`, `queries/useBatchRunStatus.ts`
- `components/common/ManualBatchTrigger.tsx` — 수동 재연동 버튼
- `types/auth.ts` — UserRole에 `HQ_MARKETING`/`HQ_COMPLIANCE` 추가
- `App.tsx` — `registerTokenGetter(getStoredToken)` 호출 추가 (현재 누락)

### 9.4 빌드 및 배포

```bash
cd /home/ubuntu/c-maker/frontend
npm ci
npm run build    # dist/ 생성
# serve가 dist/를 :8080에서 서빙 (systemd 서비스)
```

---

## 10. 배치 파이프라인

### 10.1 일간 배치 (`run_daily.py`) — 07:30 SLA

```
06:00 시작
  │
  ├─ connectors: 소스별 수집 + DATA_SOURCE_SNAPSHOT 적재
  │   (장애 시 → 전일 스냅샷 폴백, RULE-SENSE-04)
  │
  ├─ normalizers: SIGNAL 정규화 + scope 태깅
  │
  ├─ sensing: 임계치 판정 → EVENT 승격
  │   쿨다운(14일) / 상한(8건) / 병합 처리
  │
  ├─ targeting: 배제 → 스코어링 → TOP 20
  │   Score = (Σwᵢ·sᵢ + R) × 근접도 × 규모적합도
  │   탐색 슬롯 3건 (톰슨 샘플링)
  │
  ├─ briefing: LiteLLM Gateway 브리프 생성
  │   프롬프트 엔지니어링 (Chat Completion)
  │
  └─ export: RECOMMENDATION + BRIEF DB 적재

07:30 이전 완료 (P95 SLA)
```

### 10.2 수동 재실행 (REQ-17)

API 서버의 `batch.service.py`가 `subprocess.Popen`으로 `run_daily.py`를 별도 프로세스로 기동하고 즉시 응답한다. 프론트엔드는 `BATCH_RUN` 상태를 폴링해 완료를 감지한다.

### 10.3 cron 스케줄

> **현행 확인 (2026-09-30)**: `/etc/cron.d/c-maker`로 등록 완료. 저장소의 `deploy/c-maker.cron`이 기준 파일이다.

**⚠ 서버 타임존이 Asia/Seoul이어야 한다.**

Ubuntu의 cron(3.0pl1)은 **`CRON_TZ`/`TZ`로 스케줄 타임존을 지정할 수 없다.** `man 5 crontab` LIMITATIONS 절에 따르면 크론탭의 `TZ`는 실행되는 명령의 환경변수에만 적용되고 작업 실행 시각에는 영향을 주지 않는다. 스케줄은 항상 서버 타임존을 따른다.

EC2 기본값은 `Etc/UTC`이므로 그대로 두면 `0 6 * * *`이 **15:00 KST**에 돌아 07:30 SLA를 놓친다. 서버 타임존을 먼저 맞춘다.

```bash
sudo timedatectl set-timezone Asia/Seoul
timedatectl    # Time zone: Asia/Seoul (KST, +0900) 확인
```

> 서버를 UTC로 유지해야 하는 환경이라면 시각을 UTC로 환산한다(일간 06:00 KST = `0 21 * * *`, 전일 21:00 UTC).
> PostgreSQL은 `postgresql.conf`에 `timezone`/`log_timezone`이 `Etc/UTC`로 고정돼 있어 OS 타임존을 따라가지 않는다. 앱의 업무 날짜는 `common/config.py`의 `now_kst()`/`today_kst()`가 `ZoneInfo("Asia/Seoul")`을 명시하므로 OS 타임존과 무관하다.

**등록 — 사용자 크론탭(`crontab -e`)이 아니라 `/etc/cron.d`를 쓴다.**

아래 항목은 시각 필드 5개 뒤에 **실행 사용자(`ubuntu`)**가 들어가는 `/etc/cron.d` 형식이다. `crontab -e`에 그대로 붙여넣으면 사용자 필드 때문에 실패한다.

```bash
sudo install -o root -g root -m 644 deploy/c-maker.cron /etc/cron.d/c-maker
sudo systemctl restart cron
```

> **⚠ 줄끝은 LF여야 한다.** CRLF면 cron이 `Error: bad minute`을 내고 **파일 전체를 무시한다.** 아무 로그도 남지 않아 조용히 배치가 죽는다(2026-09-30 실제 발생).
> 저장소에 `.gitattributes`로 `deploy/* text eol=lf`를 걸어 두었으나, Windows에서 편집한 파일을 `scp`로 직접 올릴 때는 여전히 깨질 수 있다. 설치 후 아래로 확인한다.
>
> ```bash
> file /etc/cron.d/c-maker          # "CRLF line terminators"가 나오면 안 된다
> sudo sed -i 's/\r$//' /etc/cron.d/c-maker && sudo systemctl restart cron   # 깨졌을 때 교정
> sudo journalctl -u cron --since '-1min' | grep -iE 'error|syntax'          # 출력이 없어야 정상
> ```

```bash
# 시각은 KST 기준 (서버 TZ = Asia/Seoul 전제)
SHELL=/bin/bash

# 일간 배치 — 매일 06:00 KST (07:30 SLA)
0 6 * * * ubuntu cd /home/ubuntu/c-maker && .venv/bin/python -m backend.batch.run_daily >> /var/log/c-maker/cron-daily.log 2>&1

# 월간 모집단 적재 — 매월 1일 01:00 KST
0 1 1 * * ubuntu cd /home/ubuntu/c-maker && .venv/bin/python -m backend.batch.run_monthly >> /var/log/c-maker/cron-monthly.log 2>&1

# 지오코딩 — 10분마다 (타임존 무관)
*/10 * * * * ubuntu cd /home/ubuntu/c-maker && .venv/bin/python -m backend.batch.geocoding.geocode_job >> /var/log/c-maker/cron-geocode.log 2>&1
```

리다이렉트 대상이 `cron-*.log`인 이유는 §10.4를 참고한다. `LOG_DIR`이 설정되면 배치가 직접 `daily.log`·`monthly.log`·`geocode.log`에 쓰기 때문에, cron 리다이렉트를 같은 이름으로 두면 한 파일에 두 경로가 섞인다.

**등록 확인**

```bash
sudo journalctl -u cron --since '-15min' | grep CMD    # 실행 이력
tail -5 /var/log/c-maker/geocode.log                   # 10분 주기 잡이 가장 먼저 찍힌다
```

### 10.4 배치 로그

Python `logging` 모듈로 구조화 로그 (OPS-08):
- 기록 항목: 단계별 처리 건수, 소요시간, 실패 소스명
- 타임스탬프는 `log_setup.py`가 **UTC로 고정**해 찍는다(`datetime.fromtimestamp(record.created, UTC)`). 서버 타임존을 KST로 바꿔도 로그의 `ts`는 `+00:00`을 유지하므로 과거 로그와 형식이 섞이지 않는다.

`.env`의 `LOG_DIR` 설정에 따라 출력 위치가 갈린다.

| `LOG_DIR` | 출력 |
|---|---|
| 설정됨 (예: `/var/log/c-maker`) | `<LOG_DIR>/<name>.log`에 **파일로만** 쓴다 — `daily.log`, `monthly.log`, `geocode.log`, `api.log` |
| 비어 있음 | stdout (cron 리다이렉트·journald가 수집) |

> `LOG_DIR`이 설정된 상태에서는 배치가 이미 `daily.log`에 직접 쓰므로, cron 리다이렉트는 **다른 이름**(`cron-daily.log`)으로 둔다(§10.3). 같은 이름을 쓰면 한 파일에 두 경로가 섞인다. `cron-*.log`에는 정상 동작 시 아무것도 남지 않고, 파이썬이 뜨기 전에 죽는 경우(경로 오류, venv 누락 등)의 stderr만 잡힌다.

```bash
sudo mkdir -p /var/log/c-maker
sudo chown ubuntu:ubuntu /var/log/c-maker
```

---

## 11. 백엔드 외부 호출 3경로

| 경로 | 호출 주체 | 프로토콜 | 인증 | 용도 | 장애 대응 |
|---|---|---|---|---|---|
| **공공데이터 API** | 배치 connectors | HTTPS (443) | API Key (.env) | 신호 수집, 모집단 적재, 사업자 검증 | 전일 스냅샷 폴백 (RULE-SENSE-04) |
| **PostgreSQL** | API + 배치 | TCP (5432, localhost) | scram-sha-256 | 전 레이어 CRUD | 커넥션 풀 재시도 |
| **LiteLLM Gateway** | 배치 briefing | HTTPS (443) | API Key | 브리프 생성 (RULE-BRIEF) | 재시도 + 타임아웃 |

---

## 12. systemd 서비스

> **사전 조치**: Tomcat이 설치되어 있다면 8080 포트 충돌을 방지하기 위해 먼저 비활성화한다.
> ```bash
> sudo systemctl stop tomcat && sudo systemctl disable tomcat
> ```
> 현행 서버에서는 2026-09-29에 완료됨.

### 12.1 FastAPI (`c-maker-api.service`)

```ini
[Unit]
Description=C-MAKER FastAPI
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/c-maker
EnvironmentFile=/home/ubuntu/c-maker/.env
ExecStart=/home/ubuntu/c-maker/.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 12.2 프론트엔드 (`c-maker-frontend.service`)

> **참고**: nvm 환경에서 `npm install -g serve`로 설치하면 serve 바이너리가 `/usr/bin/serve`가 아닌 nvm 경로에 위치할 수 있다. 아래 명령으로 실제 경로를 확인한 뒤 `ExecStart`를 맞춘다.
> ```bash
> which serve   # 예: /home/ubuntu/.nvm/versions/node/v24.21.0/bin/serve
> ```

```ini
[Unit]
Description=C-MAKER Frontend (serve)
After=network.target

[Service]
User=ubuntu
# ※ which serve 결과로 아래 경로를 교체할 것
ExecStart=/home/ubuntu/.nvm/versions/node/v24.21.0/bin/serve -s /home/ubuntu/c-maker/frontend/dist -l 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 12.3 서비스 등록

```bash
sudo cp deploy/c-maker-api.service /etc/systemd/system/
sudo cp deploy/c-maker-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now c-maker-api
sudo systemctl enable --now c-maker-frontend
```

---

## 13. 배포 절차

### 13.1 초기 배포

> **전제**: §1.3의 패키지 설치와 Tomcat 비활성화(§12)가 완료된 상태에서 진행한다.

```bash
# 0) 기존 Tomcat/Nginx 정리 (이미 완료된 경우 생략)
sudo systemctl stop tomcat 2>/dev/null && sudo systemctl disable tomcat 2>/dev/null
sudo cp /etc/nginx/sites-available/myapp /etc/nginx/sites-available/myapp.bak 2>/dev/null
sudo rm -f /etc/nginx/sites-enabled/myapp

# 기존 수동 실행 uvicorn이 있다면 종료
sudo ss -tlnp | grep :8000 && echo "8000 포트 점유 프로세스가 있으면 PID 확인 후 sudo kill <PID>"

# 1) 소스
cd /home/ubuntu
git clone <repository-url> c-maker
cd c-maker

# 2) Python 가상환경 + 백엔드 의존성
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 3) DB 스키마 적용 (기존 myapp_db / myapp_user 사용, 신규 생성 없음)
psql -U myapp_user -d myapp_db -c "\dt"   # 기존 테이블 충돌 여부 확인
psql -U myapp_user -d myapp_db -f backend/database/schema.sql

# 4) 초기 데이터 (BRANCH + USER + THRESHOLD_CONFIG)
psql -U myapp_user -d myapp_db -f backend/database/seed.sql

# 5) 프론트엔드 (nvm Node.js v24 사용)
cd frontend && npm ci && npm run build && cd ..

# 6) Nginx
sudo cp deploy/c-maker.nginx.conf /etc/nginx/sites-available/c-maker
sudo ln -sf /etc/nginx/sites-available/c-maker /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 7) systemd 서비스
sudo cp deploy/c-maker-api.service /etc/systemd/system/
sudo cp deploy/c-maker-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now c-maker-api
sudo systemctl enable --now c-maker-frontend

# 8) 로그 디렉토리
sudo mkdir -p /var/log/c-maker && sudo chown ubuntu:ubuntu /var/log/c-maker

# 9) cron 등록
crontab -e   # §10.3 내용 입력

# 10) 첫 모집단 적재
source .venv/bin/activate
python -m backend.batch.run_monthly
```

### 13.2 업데이트 배포

```bash
cd /home/ubuntu/c-maker
git pull origin main

# 백엔드
source .venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart c-maker-api

# 프론트엔드 (변경 시)
cd frontend && npm ci && npm run build
# serve가 dist/를 직접 서빙하므로 서비스 재시작 불필요
# (파일이 교체되면 다음 요청부터 반영)
```

---

## 14. 구현 순서 (스프린트별)

`7-execution-plan.md` v1.4.0 기준, EC2 배포 환경에 맞게 재정리.

### 스프린트 0 (1주) — 인프라 + 셋업

| 작업 | 내용 |
|---|---|
| EC2 | Ubuntu 26.04, Python/Node/PostgreSQL/Nginx/serve 설치 |
| DB | `schema.sql` 적용, 트리거(CONST-19) 동작 확인 |
| 백엔드 골격 | FastAPI 앱, JWT 미들웨어, 에러 핸들러, DB 커넥션 풀 |
| Nginx + systemd | 리버스 프록시, c-maker-api/frontend 서비스 등록 |
| LLM 연결 | `openai` 패키지 + LiteLLM Gateway 테스트 호출 |

### 스프린트 1~2 (2주) — 모집단 적재 + 사업자 검증

| 작업 | 관련 |
|---|---|
| `sbiz_connector.py` | S-1 상가(상권)정보 전수 |
| `permit_connector.py` | F-2 인허가 전수 파일 |
| `common/geo.py` | EPSG:5174 → WGS84 (VAL-11) |
| `business_loader.py` + `run_monthly.py` | BUSINESS 적재 (UC-17) |
| `nts_connector.py` | S-8 국세청 보완 검증 (UC-03) |
| `geocode_job.py` | 지점 좌표 (RULE-BRANCH-03) |

### 스프린트 3~4 (2주) — 일간 신호 + 접촉 명부 + API 연동

| 작업 | 관련 |
|---|---|
| 커넥터 6종 | 인허가 변동분, 지하철, ECOS, 오피넷, 기상청, 재난문자 |
| normalizers + sensing | SIGNAL 정규화, EVENT 승격 |
| targeting | 배제·스코어링·탐색슬롯 |
| briefing | LiteLLM Gateway 브리프 생성 |
| `run_daily.py` | 파이프라인 통합 |
| API | 추천/브리프 조회 엔드포인트 |
| 프론트엔드 | mock → apiFetch 교체, mockData.ts 삭제 |

### 스프린트 5 (2주) — 태깅 + CRM + 임계치

| 작업 | 관련 |
|---|---|
| 태깅 API | UC-09 (VAL-06) |
| CRM 파일 API | UC-08 (CSV/XLSX) |
| 임계치 API | UC-15 (VAL-05, REQ-15 이력) |
| 감사 로그 | REQ-15 |

### 스프린트 6 (2주) — 수동 재연동 + 안정화

| 작업 | 관련 |
|---|---|
| 배치 재실행 API | UC-18 (subprocess.Popen, RULE-SENSE-06, VAL-12) |
| ManualBatchTrigger | 프론트엔드 버튼 + 상태 폴링 |
| SLA 모니터링 | 07:30 완료 로그 체크 |
| 파일럿 온보딩 | BRANCH + USER + THRESHOLD_CONFIG psql 적재 |

---

## 15. 테스트 전략

| 우선순위 | 대상 | 방법 |
|---|---|---|
| **1 (필수)** | 이벤트 승격 판정 (5.1절) | 단위 테스트 |
| **2 (필수)** | 배제 (RULE-TARGET-01), 스코어링 (RULE-TARGET-02) | 단위 테스트 |
| **3 (필수)** | 브리프 그라운딩 (RULE-BRIEF-02) | 회귀 테스트셋 |
| **4** | CRUD 엔드포인트 | Postman / 통합 테스트 |
| **5** | 프론트엔드 | SC-01~09 시나리오 수동 확인 |
| lint | 백엔드 ruff + mypy, 프론트엔드 ESLint |

---

## 16. 기존 설계 문서(1~9)와의 차이

본 구현 가이드(10번)는 실제 구현 환경을 확인한 뒤 작성되었으므로, 설계 시점에 작성된 1~9번 문서와 일부 차이가 있다. **구현 시에는 본 문서(10번)를 최종 기준으로 따른다.**

| 항목 | 기존 문서 서술 | 본 문서 (구현 기준) | 차이 이유 |
|---|---|---|---|
| **LLM 호출 경로** | AWS Bedrock AI Agent + Action Group + Knowledge Base (`2-prd.md` §5, `4-project-principle.md` §2) | LiteLLM Gateway + `openai` 패키지 + Chat Completion API | 실제 제공된 LLM 환경이 Bedrock 직접 호출이 아닌 LiteLLM Gateway(OpenAI-Compatible) |
| **briefing 파일명** | `bedrock_agent_client.py` (`4-project-principle.md` §6) | `llm_client.py` | Bedrock Agent 전용이 아니므로 범용 이름으로 변경 |
| **LLM 의존성** | `boto3` (IAM 자격증명 기반) | `openai` 패키지 (`base_url` 변경), boto3 불필요 | Gateway가 인증을 중계하므로 AWS SDK 불필요 |
| **OPS-01 환경변수** | IAM 역할/자격증명, Agent ID, KB ID (`4-project-principle.md` §5) | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_DISABLE_THINKING` | Gateway 방식이므로 IAM 대신 Virtual Key |
| **PRIN-08 재현성** | `temperature=0` 으로 동일 입력 → 동일 출력 | `temperature` 미전송 (게이트웨이가 `temperature=1` 외 거부) | §8.2 실측 제약. 재현성은 프롬프트·사실 문장 고정으로만 확보 |
| **UC-07 브리프 생성 5초** | 브리프 1건 5초 이내 | **충족** — EC2 실측 median 3.77초 / max 4.61초 (n=5) | §8.5. 개발 PC(7.4초) 기준으로 판단하면 미달로 오판한다 |
| **OPS-06 호출 격리** | Bedrock AI Agent 호출로 한정 (`4-project-principle.md` §5) | LiteLLM Gateway Chat Completion으로 한정 — `briefing`/`campaign` 모듈에서만 호출하는 원칙은 동일 | 호출 대상만 변경, 격리 원칙 유지 |
| **RAG (상품설명서)** | Bedrock Knowledge Base에 색인, Agent가 직접 조회 (`2-prd.md` §5) | MVP에서는 미구현 (REQ-11은 Phase 2). 필요 시 별도 RAG 파이프라인 구축 | Agent/KB 연동이 없으므로 자체 구축 필요, Phase 2에서 결정 |

> 기존 문서(1~9번)의 Bedrock 관련 서술은 설계 시점의 결정 이력으로 보존한다. 수정하지 않는다.

---

## 17. 미확정 사항

| # | 항목 | 상태 | 조치 |
|---|---|---|---|
| 1 | 지방행정 인허가 변동분 API 신청 (N-1) | ❌ 미신청 | 즉시 data.go.kr 활용신청 |
| 2 | S-1 좌표계·사업자번호 제공 여부 | 미확인 | 테스트 호출로 확인 |
| 3 | ECOS / 오피넷 별도 포털 가입 | 미완료 | ecos.bok.or.kr, opinet.co.kr |
| 4 | ~~LiteLLM Gateway 인증키 형식~~ | ✅ **해소(2026-09-30)** — Virtual Key(`sk-...`)를 `Authorization: Bearer`로 전송. 실제 호출 성공 | — |
| 5 | ~~LLM 모델 확정~~ | ✅ **해소(2026-09-30)** — `claude-opus-5` | 제공 모델 목록은 §8.1 |
| 6 | ~~UC-07 "브리프 1건 5초" 미달성~~ | ✅ **해소(2026-09-30)** — EC2 실측 median 3.77초로 충족(§8.5). 개발 PC 수치(7.4초)로 인한 오판이었다 | 07:30 전체 SLA는 TOP20 × 지점 수로 별도 측정 필요 |
| 7 | 07:30 배치 전체 SLA | 미측정 | 브리프 1건은 확인. 파일럿 지점 수 확정 후 `run_daily.py` 전체 실행 시간 측정 |

### 17.1 해소된 인프라 사항 (2026-09-29)

| 항목 | 결과 | 비고 |
|---|---|---|
| Tomcat ↔ serve 8080 포트 충돌 | ✅ 해소 | Tomcat disable, serve가 8080 사용 |
| Nginx myapp ↔ c-maker 설정 충돌 | ✅ 해소 | myapp.bak 백업, c-maker 적용 |
| PostgreSQL DB/계정 결정 | ✅ 확정 | 기존 `myapp_db`/`myapp_user` 사용, 신규 생성 없음 |
| Node.js 버전 (v24 vs v20) | ✅ 확인 | nvm v24 현행 사용, 빌드 호환 문제 없음 |
| Python 3.14 패키지 호환성 | ⚠️ 모니터링 | python-jose 빌드 실패 시 PyJWT 대체 |

---

## 18. 프로젝트명 변경 사항

| 변경 전 | 변경 후 |
|---|---|
| BranchSense / branchsense | **C-MAKER** / **c-maker** |

기존 설계 문서(`1-domain-definition.md` ~ `9-style-guide.md`)의 "BranchSense" 표기는 C-MAKER로 일괄 변경 완료. 본 구현 가이드는 C-MAKER 명칭으로 작성되었다.

---

## 19. 파일 구조 요약

```
c-maker/                              # /home/ubuntu/c-maker
├── .venv/                            # Python 가상환경
├── .env                              # 환경변수 (커밋 안 함)
├── .env.example                      # 변수명만 (커밋함)
├── .gitignore
├── backend/
│   ├── api/                          # FastAPI 서버
│   ├── batch/                        # 배치 파이프라인
│   ├── common/                       # 공유 유틸리티
│   ├── database/
│   │   ├── schema.sql                # DDL
│   │   └── seed.sql                  # 초기 데이터 (BRANCH, USER, THRESHOLD_CONFIG)
│   └── requirements.txt
├── frontend/
│   ├── src/                          # React 19 + TypeScript
│   ├── dist/                         # 빌드 산출물 (serve가 서빙)
│   ├── package.json
│   └── vite.config.ts
├── deploy/
│   ├── c-maker.nginx.conf
│   ├── c-maker-api.service
│   └── c-maker-frontend.service
└── docs/                             # 설계 문서
```
