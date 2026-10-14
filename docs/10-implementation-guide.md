# C-MAKER 구현 가이드

- **버전**: v2.3.0
- **작성일**: 2026-09-29
- **최종 수정일**: 2026-10-14
- **목적**: EC2 단일 인스턴스에 프론트엔드·백엔드·DB를 구성하고, MVP 기능을 구현하기 위한 종합 구현 계획서
- **작성 방법**: grill-me 방식으로 39개 설계 결정을 확정한 뒤 작성
- **v2.1.0 변경**: EC2 서버 현행 구성(Tomcat→serve 전환 완료, Node.js v24/nvm, Python 3.14.4, PostgreSQL 18.6) 반영
- **v2.2.0 변경**: DB를 기존 `myapp_db`/`myapp_user` 사용으로 확정. `cmaker`/`cmaker_app` 신규 생성 관련 내용 전면 삭제
- **v2.3.0 변경 (2026-10-14)**: 현재 구현 기준 현행화. DB/유저는 기존 `myapp_db`/`myapp_user`, 테이블은 전용 스키마 `cmaker`로 정리(§4). Nginx 보안 헤더·TLS 경고(§2), 환경변수 전체 목록(§3), 실제 `backend/` 트리·동기 `ConnectionPool`(§5.1), 의존성 PyJWT·openpyxl·tzdata(§5.2), API 엔드포인트·에러 코드·응답 필드 전체(§6), 테이블 15개·인덱스 15개·seed/패치 절차(§7·§13), 프롬프트 `brief-v5`·3문장 화법·citation guard 검사 순서(§8), 프론트엔드 실 API 연동 완료(§9), 일간 배치 이벤트 상한 12건·명부 다양성 상한·행안부 업종별 인허가 API(§10.1), `KillMode=process`(§12.1), 테스트 파일 목록(§15, 2026-10-14 pytest 재실행은 환경 미비로 미완료) 반영. "CRM 파일" 표기를 "CRM 등록 파일"로 통일

---

## 참조 문서

| 문서 | 버전 | 역할 |
|---|---|---|
| `1-domain-definition.md` | v1.5.0 | REQ, VAL, RULE, UC, 엔티티 정의 |
| `2-prd.md` | v1.5.0 | 비즈니스 목표, 기술 스택, 비기능 요건 |
| `3-user-scenario.md` | v1.4.0 | SC-01~09 사용 흐름 |
| `4-project-principle.md` | v1.6.0 | 디렉토리 구조, 레이어 원칙, 네이밍 |
| `5-arch-diagram.md` | v1.4.0 | 시스템 구성도, 배치 파이프라인 |
| `6-erd.md` | v1.5.0 | DB 스키마, 제약사항, 인덱스, 초기 데이터 |
| `7-execution-plan.md` | v1.5.0 | 스프린트별 작업 항목, MVP 구현 현황 |
| `8-wireframe.md` | v1.4.0 | 화면 레이아웃 |
| `9-style-guide.md` | v1.5.0 | 디자인 토큰, 컴포넌트 스타일 |
| `crm-integration.md` | v1.1.0 | CRM 등록 파일 컬럼·대상 행·형식 |
| `public data sources.md` | v1.3.0 | 공공데이터 API 신청 현황, 인증키 관리, 인허가 API 연동 정보 |
| `api/11-api-spec.md` | — | 행안부 업종별 인허가·국민연금 API 요청/응답 명세 |

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
>
> 저장소의 기준 파일은 `deploy/c-maker.nginx.conf`이다. 아래 코드블록은 그 파일과 같은 내용이다(2026-10-14 대조).

> [!WARNING]
> **⚠ 현재 구성은 HTTP(80)만 연다. 로그인 토큰이 평문으로 오가므로 내부망 외 노출 시 TLS(443) 적용이 필요하다.** (`deploy/c-maker.nginx.conf` 주석)

```nginx
# /etc/nginx/sites-available/c-maker  (docs/10-implementation-guide.md §2)
#
# 설치:
#   sudo cp deploy/c-maker.nginx.conf /etc/nginx/sites-available/c-maker
#   sudo ln -sf /etc/nginx/sites-available/c-maker /etc/nginx/sites-enabled/
#   sudo nginx -t && sudo systemctl reload nginx
#
# ⚠ 현재 구성은 HTTP(80)만 연다. 로그인 토큰이 평문으로 오가므로 내부망 외 노출 시 TLS(443) 적용이 필요하다.

server {
    listen 80;
    server_name _;

    server_tokens off;

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
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy same-origin always;
}
```

- `server_tokens off`: 응답 헤더·에러 페이지에 Nginx 버전을 노출하지 않는다.
- `add_header ... always`: 4xx/5xx 응답(예: API의 401·403·429)에도 보안 헤더를 붙인다. `always`가 없으면 2xx/3xx에만 붙는다.

```bash
# 기존 myapp 설정 백업 (이미 완료된 경우 생략)
sudo cp /etc/nginx/sites-available/myapp /etc/nginx/sites-available/myapp.bak 2>/dev/null
sudo rm -f /etc/nginx/sites-enabled/myapp

sudo ln -sf /etc/nginx/sites-available/c-maker /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 3. 환경변수

설정은 `backend/common/config.py`의 `Settings`(pydantic-settings)가 저장소 루트 `.env`에서 읽는다. 변수명은 대소문자를 구분하지 않으며(`DB_SCHEMA` → `db_schema`), `.env`에 없는 키는 `Settings`의 기본값을 쓴다. systemd는 `EnvironmentFile=`로 같은 파일을 프로세스 환경에 싣는다(§12.1).

### 3.1 `.env` (저장소 루트, .gitignore에 포함)

`.env.example`을 복사해 값을 채운다. 아래 `<...>`는 자리표시이며 실제 값을 문서·저장소에 적지 않는다.

```bash
# ── 실행 환경 ──
APP_ENV=prod                      # dev면 /api/docs 노출, JWT_SECRET 미설정 시 임시 키, 개발용 픽스처 허용

# ── DB (기존 myapp_db / myapp_user 사용) ──
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp_db
DB_USER=myapp_user
DB_PASSWORD=<myapp_user 비밀번호>
DB_SCHEMA=cmaker                  # C-MAKER 전용 스키마(§4). 영소문자·숫자·밑줄만 허용

# ── JWT ──
JWT_SECRET=<32자 이상 무작위 문자열>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# ── 공공데이터 API ──
DATA_GO_KR_SERVICE_KEY=<data.go.kr 인증키>
ECOS_API_KEY=<한국은행 ECOS 인증키>
OPINET_API_KEY=<오피넷 인증키>
VWORLD_API_KEY=<VWorld 지오코더 인증키>   # 지점 주소 → 좌표(RULE-BRANCH-03)
PERMIT_FULL_DATA_DIR=             # 인허가 전수 CSV 디렉터리(월간). 비우면 해당 소스 skip(§10.2)

# ── LLM (LiteLLM Gateway, OpenAI-Compatible) ──
# base_url은 /v1 까지 포함한다 (openai 패키지가 /chat/completions를 붙인다). 비우면 화법은 TEMPLATE
LLM_BASE_URL=https://frontier-llmgw.aipocnhbank.com/v1
LLM_API_KEY=<LiteLLM Virtual Key, sk-...>
LLM_MODEL=claude-opus-5
LLM_TIMEOUT_SECONDS=10
LLM_DISABLE_THINKING=true

# ── 배치 ──
BATCH_COOLDOWN_MINUTES=30
LOG_DIR=/var/log/c-maker          # 비우면 stdout(§10.5)

# ── 서버 ──
FRONTEND_ORIGIN=http://localhost  # CORS 허용 origin, 쉼표 구분. 와일드카드 금지(OPS-07)
```

**`JWT_SECRET` 규칙** (`backend/api/security.py`): 값이 없거나 **32자 미만이면 운영(`APP_ENV`≠`dev`)에서는 API 기동을 거부**한다(`app.py` lifespan에서 `get_jwt_secret()` 호출). `APP_ENV=dev`일 때만 경고 로그와 함께 프로세스마다 임시 키를 만들며, 재기동하면 기존 토큰이 무효가 된다. 생성 예: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 3.2 `frontend/.env` (선택)

```bash
VITE_API_BASE_URL=/api
```

`frontend/src/api/client.ts`는 `VITE_API_BASE_URL`이 없으면 `/api`를 쓴다. Nginx가 같은 origin에서 `/api/`를 프록시하므로 기본 구성에서는 파일이 없어도 된다(2026-10-14 기준 저장소에 `frontend/.env` 없음).

### 3.3 `.env.example` (커밋 대상, 키 없이 변수명만)

저장소 루트 `.env.example`의 키 목록이다(파일에는 항목별 설명 주석이 함께 있다).

```bash
APP_ENV=prod
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp_db
DB_USER=
DB_PASSWORD=
DB_SCHEMA=cmaker
JWT_SECRET=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
DATA_GO_KR_SERVICE_KEY=
ECOS_API_KEY=
OPINET_API_KEY=
VWORLD_API_KEY=
PERMIT_FULL_DATA_DIR=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=claude-opus-5
LLM_TIMEOUT_SECONDS=10
LLM_DISABLE_THINKING=true
BATCH_COOLDOWN_MINUTES=30
LOG_DIR=
FRONTEND_ORIGIN=http://localhost
```

### 3.4 선택 변수 (`Settings`에만 있음, 기본값)

`.env.example`에는 없지만 `.env`에 적으면 덮어쓸 수 있는 키다.

| 변수 | 기본값 | 용도 |
|---|---|---|
| `DB_POOL_MIN_SIZE` | `1` | 커넥션 풀 최소 크기(`common/db/pool.py`) |
| `DB_POOL_MAX_SIZE` | `10` | 커넥션 풀 최대 크기 |
| `SNAPSHOT_ARCHIVE_DIR` | `<저장소>/data/snapshots` | 파일형 원본(인허가 전수 CSV 등) 보관 디렉터리(OPS-05) |
| `EXTERNAL_HTTP_TIMEOUT_SECONDS` | `15.0` | 공공 API 공통 타임아웃(초, `connectors/http_client.py`). PERMIT_DAILY만 `pipeline.toml`의 `timeout_seconds`(90초)를 따로 쓴다 |
| `LLM_MAX_CONCURRENCY` | `4` | 브리프 생성 LLM 동시 호출 수(`run_daily.py` ThreadPoolExecutor) |
| `BATCH_STALE_MINUTES` | `180` | `RUNNING`으로 이 시간(분) 이상 남은 실행을 비정상 종료로 보고 `FAILED` 처리 |

---

## 4. PostgreSQL 초기화

> **현행 확인 (2026-09-29)**: 서버에 PostgreSQL 18.6 가동 중. 기존에 생성된 **`myapp_db` (owner: `myapp_user`)를 C-MAKER 운영 DB로 사용한다.** 신규 DB/유저는 생성하지 않는다.

**테이블은 전용 스키마 `cmaker`에 만든다.** 공유 DB인 `myapp_db`의 기존 테이블과 이름이 충돌하지 않게 하기 위해서다.

- `backend/database/schema.sql`이 맨 앞(헤더 주석 다음)에서 `CREATE SCHEMA IF NOT EXISTS cmaker;` → `SET search_path TO cmaker;`를 실행한 뒤 테이블을 만든다. 스키마도 이 파일이 생성하므로 별도 생성 단계는 없다.
- 앱(API·배치)은 `backend/common/db/pool.py`가 모든 커넥션을 `-c search_path=<DB_SCHEMA> -c timezone=Asia/Seoul`로 연다(`DB_SCHEMA` 기본 `cmaker`). SQL에는 스키마 접두어를 쓰지 않는다.
- `seed.sql`·패치 파일도 첫머리에서 `search_path`를 `cmaker`로 지정한다. 운영자가 psql로 직접 조회할 때는 `cmaker.branch`처럼 스키마를 붙이거나 `SET search_path TO cmaker;`를 먼저 실행한다.
- BRANCH 트리거 함수는 `SET search_path = cmaker, pg_temp`로 고정돼 있어, 기본 search_path로 접속한 psql 세션에서 `UPDATE branch`를 해도 `cmaker.branch_history`에 기록된다(§7.2).

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

# 테이블 생성 확인 (cmaker 스키마, 15개)
psql -U myapp_user -d myapp_db -c "\dt cmaker.*"
```

> **참고**: C-MAKER 테이블은 `cmaker` 스키마에 생기므로 `public` 등 기존 스키마의 같은 이름 테이블(`branch`, `event` 등)과 충돌하지 않는다. 그냥 `\dt`는 기본 search_path(`"$user", public`) 기준이라 C-MAKER 테이블이 보이지 않을 수 있다. 반드시 `\dt cmaker.*`로 확인한다.

---

## 5. 백엔드 구조

### 5.1 디렉토리 (실제 트리, 2026-10-14 기준)

`4-project-principle.md` §6의 설계 구조를 따르되, 파일명은 Python 모듈 규칙에 맞춰 밑줄 표기(`auth_router.py`)를 쓴다. `__init__.py`·`__pycache__`는 생략했다.

```
backend/
├── batch/
│   ├── connectors/                 # 소스별 원본 수집
│   │   ├── http_client.py           # 공통 HTTP 호출(requests, EXTERNAL_HTTP_TIMEOUT_SECONDS)
│   │   ├── sbiz_connector.py        # 소진공 상가(상권)정보 (S-1, REQ-16)
│   │   ├── nts_connector.py         # 국세청 사업자등록상태 (S-8, REQ-02)
│   │   ├── permit_connector.py      # 행안부 업종별 인허가 변동분 API + 전수 CSV 읽기 (F-2/N-1)
│   │   ├── kma_connector.py         # 기상청 특보 (S-2)
│   │   ├── kma_forecast_connector.py # 기상청 단기·중기예보, 초단기실황 (S-4/S-5)
│   │   ├── ecos_connector.py        # 한국은행 ECOS 원/달러
│   │   ├── opinet_connector.py      # 오피넷 시도별 유가
│   │   └── vworld_connector.py      # VWorld 지오코더 (지점 주소 → 좌표)
│   ├── population/                 # 사업체 모집단 적재 (REQ-16)
│   │   └── business_loader.py
│   ├── normalizers/
│   │   ├── signal_normalizer.py     # SIGNAL 정규화 + scope 태깅
│   │   ├── forecast_normalizer.py   # 예보 신호·날씨 참고 판정
│   │   └── permit_parser.py         # 인허가 행 파싱·영업상태 매핑·보건소류 제외
│   ├── sensing/                    # 이벤트 승격 (도메인 정의서 5.1절)
│   │   ├── threshold_engine.py
│   │   └── event_promoter.py
│   ├── targeting/                  # 배제·스코어링·명부 다양성 상한·탐색슬롯
│   │   ├── exclusion.py
│   │   ├── scorer.py
│   │   ├── reason_tier.py
│   │   └── exploration.py
│   ├── briefing/                   # 브리프 생성
│   │   ├── fact_builder.py          # 사실 문장·1줄 요약·연락 사유/목적(결정론)
│   │   ├── llm_client.py            # openai 패키지, base_url=LiteLLM Gateway
│   │   ├── brief_generator.py       # 프롬프트(brief-v5)·LLM/TEMPLATE/REASON_ONLY
│   │   └── citation_guard.py        # 출처 태그·금칙·예보 단정·상품어·근거 없는 수치 후처리 검증
│   ├── geocoding/
│   │   └── geocode_job.py
│   ├── batch_repository.py         # 배치 전용 SQL (판정·채점 로직은 DB를 모르는 순수 함수)
│   ├── run_daily.py
│   └── run_monthly.py
├── api/
│   ├── routers/
│   │   ├── auth_router.py
│   │   ├── recommendations_router.py
│   │   ├── tags_router.py
│   │   ├── thresholds_router.py
│   │   └── batch_router.py          # /batch/* + /data-freshness
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── recommendation_service.py # 목록·요약·브리프·CRM 등록 파일
│   │   ├── tag_service.py
│   │   ├── threshold_service.py
│   │   └── batch_service.py
│   ├── repositories/
│   │   ├── user_repository.py
│   │   ├── recommendation_repository.py
│   │   ├── tag_repository.py
│   │   ├── threshold_repository.py
│   │   ├── batch_run_repository.py
│   │   └── audit_repository.py      # AUDIT_LOG (REQ-15)
│   ├── middlewares/
│   │   ├── auth_middleware.py
│   │   ├── error_middleware.py
│   │   └── logging_middleware.py    # 요청 단위 접근 로그(본문·토큰 미기록)
│   ├── database.py                 # 요청 단위 커넥션 의존성(get_db)
│   ├── security.py                 # JWT 발급/검증 (PyJWT)
│   └── app.py
├── common/
│   ├── config.py                   # Settings(.env) + PipelineConfig(pipeline.toml)
│   ├── geo.py                      # EPSG:5174 → WGS84 (VAL-11)
│   ├── log_setup.py                # 구조화(JSON) 로그, UTC 타임스탬프
│   ├── snapshot_store.py           # DATA_SOURCE_SNAPSHOT 적재/조회, 파일 archive
│   ├── db/
│   │   ├── pool.py                 # psycopg 동기 ConnectionPool
│   │   └── advisory_lock.py        # 배치 공용·지오코딩 session advisory lock
│   └── schemas/                    # Pydantic 모델
│       ├── auth.py
│       ├── batch_run.py
│       ├── branch.py
│       ├── brief.py
│       ├── business.py
│       ├── event.py
│       ├── recommendation.py
│       ├── signal.py
│       └── threshold.py
├── config/
│   └── pipeline.toml               # 소스·적합도·상한·브리프 등 구조적 설정
├── database/
│   ├── schema.sql
│   ├── seed.sql
│   └── patches/
│       └── 2026-10-13_forecast_signals.sql
├── scripts/                        # 개발용(APP_ENV=dev 전용)
│   ├── load_dev_fixture.py
│   └── clear_dev_fixture.py
├── tests/                          # §15
├── requirements.txt
└── requirements-dev.txt
```

- `.env.example`은 `backend/`가 아니라 **저장소 루트**에 있다(§3.3).
- `common/db/pool.py`는 **동기 `psycopg_pool.ConnectionPool`**을 쓴다(설계 시점의 `AsyncConnectionPool` 대비 변경). FastAPI 동기(`def`) 엔드포인트가 스레드풀에서 실행되므로 이 규모에서 충분하고, psycopg 비동기 모드가 Windows `ProactorEventLoop`를 지원하지 않는 로컬 개발 문제를 피한다. 풀은 프로세스당 1회 생성하며(OPS-02), `get_connection()` 블록이 예외 없이 끝나면 commit, 예외면 rollback된다.

### 5.2 의존성 (`requirements.txt`, `requirements-dev.txt`)

> **참고**: 현행 서버 Python 3.14.4 기준(파일 주석: 로컬 3.14.6에서 설치 검증). 버전은 전부 `==`로 고정한다. JWT 라이브러리는 **PyJWT를 채택**했다 — `python-jose` 3.3.x는 알려진 취약점(CVE-2024-33663/33664)과 3.13+ 빌드 이슈가 있어 대체했다(`requirements.txt` 주석).

`backend/requirements.txt` (운영)

```
fastapi==0.119.1
uvicorn[standard]==0.54.0
psycopg[binary]==3.3.6
psycopg_pool==3.3.3
pydantic==2.13.5
pydantic-settings==2.15.0
PyJWT==2.15.1
requests==2.34.2
httpx==0.28.1
openai==1.109.1
pyproj==3.8.0
python-dotenv==1.2.3
openpyxl==3.1.5
tzdata==2026.4
```

`backend/requirements-dev.txt` (테스트·lint 전용, §15)

```
-r requirements.txt
pytest==9.1.1
ruff==0.16.9
```

| 패키지 | 용도 |
|---|---|
| `fastapi` + `uvicorn` | API 서버 |
| `psycopg` + `psycopg_pool` | PostgreSQL 접속 (ORM 없음, 직접 SQL, 동기 `ConnectionPool`) |
| `pydantic` + `pydantic-settings` | 데이터 검증·스키마 계약(PRIN-05), `.env` 로딩. `pydantic` 2.10에는 Python 3.14용 `pydantic-core` wheel이 없어 2.13.5 사용 |
| `PyJWT` | JWT 발급/검증 (HS256, `api/security.py`) |
| `requests` | 배치에서 공공 API 동기 호출 (`connectors/http_client.py`) |
| `httpx` | `backend/` 코드에서 직접 import하지 않는다. FastAPI `TestClient`(`test_api_rules.py`)가 내부적으로 사용 |
| `openai` | LiteLLM Gateway 호출 (`base_url` 변경) |
| `pyproj` | EPSG:5174 → WGS84 좌표 변환 (VAL-11) |
| `python-dotenv` | `.env` 파일 파싱 (`pydantic-settings`의 `env_file`) |
| `openpyxl` | CRM 등록 파일 XLSX 생성 (REQ-07, UC-08) |
| `tzdata` | `ZoneInfo("Asia/Seoul")`가 Windows 등 tz DB가 없는 환경에서도 동작하도록 |
| `pytest` / `ruff` | 단위 테스트 / lint (dev 전용) |

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

`backend/api/app.py`가 모든 라우터를 `/api` 접두어 아래에 묶는다. 역할 코드는 `RM`, `BRANCH_MANAGER`(지점장), `HQ_MARKETING`, `HQ_COMPLIANCE`다.

| 메서드 | 경로 | UC | 역할 제한 | 설명 |
|---|---|---|---|---|
| `GET` | `/api/health` | — | 인증 불필요 | 헬스체크 `{ "status": "ok" }` |
| `POST` | `/api/auth/login` | — | 인증 불필요 | 로그인, JWT 발급 |
| `POST` | `/api/auth/refresh` | — | 로그인 사용자 전체 | 세션 연장(새 토큰 발급). 연장 불가 계정은 403 `SESSION_NOT_EXTENDABLE` |
| `GET` | `/api/recommendations?date=` | UC-06 | RM, 지점장 | 오늘의 접촉 TOP 20 (소속 지점만) |
| `GET` | `/api/recommendations/summary?date=` | UC-06/09 | RM, 지점장 | 명부 상단 배너 요약(어제 미태깅, 상권사유비율, 외 N건) |
| `GET` | `/api/recommendations/export?date=&format=` | UC-08 | RM | CRM 등록 파일 다운로드 (CSV/XLSX) |
| `GET` | `/api/recommendations/{id}/brief` | UC-07 | RM, 지점장 | 상담 브리프 상세 |
| `POST` | `/api/recommendations/{id}/tag` | UC-09 | RM | 태깅 저장·재태깅 (VAL-06) |
| `DELETE` | `/api/recommendations/{id}/tag` | UC-09 | RM | 태깅 되돌리기(미태깅 복귀) |
| `GET` | `/api/thresholds` | UC-15 | HQ_MARKETING | 임계치 목록 |
| `PUT` | `/api/thresholds/{id}` | UC-15 | HQ_MARKETING | 임계치 변경 (VAL-05, REQ-15 이력) |
| `GET` | `/api/thresholds/{id}/history` | UC-15 | HQ_MARKETING | 변경 이력 |
| `POST` | `/api/batch/trigger` | UC-18 | 지점장, HQ_MARKETING | 수동 재실행 (RULE-SENSE-06, VAL-12) |
| `GET` | `/api/batch/status` | UC-18 | 지점장, HQ_MARKETING | 배치 상태·쿨다운 잔여 조회 |
| `GET` | `/api/data-freshness` | — | 로그인 사용자 전체 | 데이터 지연 배너 판정 (RULE-SENSE-04) |

- `date` 파라미터는 `YYYY-MM-DD`이며 생략하면 오늘(KST, `today_kst()`)이다.
- OpenAPI 문서(`/api/docs`, `/api/openapi.json`)는 `APP_ENV=dev`에서만 열린다. 운영에서는 404다.
- CORS는 `FRONTEND_ORIGIN`(쉼표 구분)만 허용하고, 메서드 `GET/POST/PUT/DELETE`, 헤더 `Authorization/Content-Type`만 받으며 `Content-Disposition`을 노출한다.

**인증·권한 세부**

- JWT는 PyJWT HS256. claim은 `sub`(사용자 ID 문자열), `role`, `branch_id`, `iat`, `exp`이며 `sub`·`exp`·`iat`는 필수다.
- 토큰 수명 = `min(계정 app_user.session_timeout_minutes, JWT_EXPIRE_MINUTES)`(최소 1분). 응답의 `sessionTimeoutMinutes`도 이 값이다.
- 요청마다 `sub`로 DB의 `app_user`를 다시 읽어 **비활성 계정이거나 role·branch_id가 토큰과 다르면 401 `INVALID_TOKEN`**으로 거부한다(권한 변경 즉시 반영).
- 역할 제한은 `auth_middleware.require_roles()` 의존성이 처리한다(OPS-03). 토큰 검증을 DB 커넥션 획득보다 먼저 해서 미인증 요청이 풀을 쓰지 않는다.
- **HQ 계정(HQ_MARKETING·HQ_COMPLIANCE)은 추천 API(목록·요약·브리프·태깅·export)에 403 `FORBIDDEN`**이다(역할 제한 + 지점 미소속 계정 거부).
- **다른 지점의 추천 ID로 브리프·태깅을 요청하면 404 `NOT_FOUND`**로 응답해 존재 여부를 드러내지 않는다. 목록·요약·export는 요청자 소속 지점만 조회하며 지점 파라미터가 없다.
- 로그인 실패는 아이디 없음·비밀번호 불일치·비활성 계정을 구분하지 않고 401 `LOGIN_FAILED` 하나로 응답한다. ⚠ 비밀번호는 결정 사항(`db-schema-decisions-review.md`)에 따라 평문 저장·`hmac.compare_digest` 비교이며, 운영 전환 전 해싱 적용을 보안팀과 재검토해야 한다(`auth_service.py` 주석).

### 6.2 공통 에러 응답 (PRIN-06)

모든 오류는 같은 형식이다. 내부 예외 상세(스택, SQL)는 응답에 싣지 않고 로그로만 남긴다(`middlewares/error_middleware.py`).

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "..." } }
```

| HTTP | code | 발생 조건 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 요청 본문·쿼리 검증 실패(FastAPI `RequestValidationError`도 **422가 아니라 400**으로 변환), 임계치 음수·비수치·정수 위반·허용 범위 초과, 부적합이 아닌 태깅에 사유 지정 |
| 400 | `REJECT_REASON_REQUIRED` | `REJECTED` 태깅에 사유 없음 (VAL-06) |
| 400 | `FIXED_THRESHOLD` | 고정 항목(`is_fixed`) 변경 시도 |
| 400 | `UNIT_MISMATCH` | 요청 `unit`이 저장된 단위와 다름 (VAL-05) |
| 401 | `UNAUTHORIZED` | 토큰 없음/Bearer 아님, 세션 연장 시 계정 사용 불가 |
| 401 | `TOKEN_EXPIRED` | 토큰 만료 |
| 401 | `INVALID_TOKEN` | 서명·형식 오류, DB의 role·branch와 불일치, 비활성 계정 |
| 401 | `LOGIN_FAILED` | 로그인 실패 |
| 403 | `FORBIDDEN` | 역할 제한, 지점 미소속 계정의 추천 API 호출 |
| 403 | `SESSION_NOT_EXTENDABLE` | `session_extendable=false` 계정의 `/auth/refresh` |
| 404 | `NOT_FOUND` | 추천·임계치 항목 없음, 다른 지점 추천, 없는 경로 |
| 405 | `METHOD_NOT_ALLOWED` | 허용되지 않은 메서드 |
| 429 | `BATCH_RUNNING` | 다른 배치가 공용 lock을 잡고 시작 중·실행 중 |
| 429 | `BATCH_COOLDOWN` | 같은 계정의 직전 수동 요청 후 `BATCH_COOLDOWN_MINUTES` 이내 (메시지에 남은 분) |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

> `ConflictError`(409 `CONFLICT`)는 클래스만 정의돼 있고 2026-10-14 기준 사용처가 없다.

### 6.3 주요 요청/응답

JSON 필드는 모두 **camelCase**다(`common/schemas/recommendation.py`의 `ApiModel`이 `to_camel` alias를 쓰고 응답도 alias로 직렬화). **페이지네이션은 없다** — 목록은 지점·일자당 최대 20건, 임계치는 전체를 한 번에 돌려준다.

**로그인 / 세션 연장**

```
POST /api/auth/login
Request:  { "username": "...(1~50자)", "password": "...(1~200자)" }
Response: { "token": "eyJ...", "expiresAt": "2026-10-14T09:30:00.123456+09:00",   // ISO 8601, KST
            "user": { "id", "name", "role", "branchId", "branchName", "branchCode",
                      "sessionTimeoutMinutes", "sessionExtendable" } }

POST /api/auth/refresh   (Authorization: Bearer ...)
Response: 로그인과 같은 형식(새 token·expiresAt)
```

본부 계정은 `branchId`·`branchName`·`branchCode`가 `null`이다.

**추천 목록**

```
GET /api/recommendations?date=2026-10-14
Response: [ { "id", "rank", "businessName", "industry", "score",
              "reasonSummary", "reasonSourceTag", "signalType", "tagStatus",
              "rejectedReason", "carriedOverFromYesterday" } ]
```

- `score`는 소수 2자리 반올림. 순위·점수는 배치가 확정한 값을 그대로 읽으며 API가 재정렬하지 않는다.
- `signalType`은 대표 신호(기여도 1위 `signal_type`), 기여 신호가 없으면 `null`.
- `tagStatus`: `UNTAGGED`/`VISITED`/`HOLD`/`REJECTED`. 브리프가 아직 없으면 `reasonSummary`는 "선정 사유 생성 중".
- 탐색 슬롯 여부는 내려주지 않는다(RULE-TARGET-04).

**명부 요약**

```
GET /api/recommendations/summary?date=2026-10-14
Response: { "date", "total", "untaggedCount", "yesterdayUntaggedCount",
            "areaReasonRatio", "areaReasonRatioLimit", "areaReasonRatioExceeded",
            "activeEventCount", "trimmedEventCount" }
```

`areaReasonRatio`는 사유 계층이 AREA만인 항목 비율(%), 기준은 THRESHOLD_CONFIG `AREA_REASON_RATIO_LIMIT`(행이 없으면 60). `trimmedEventCount`가 "외 N건"(RULE-SENSE-02)이다.

**상담 브리프**

```
GET /api/recommendations/{id}/brief
Response: { "recommendationId", "businessName", "industry", "address",
            "distanceLabel",            // "지점에서 약 0.3km"
            "recommendedOn",
            "reasonFacts": [ { "text", "sourceTag" } ],   // sourceTag = "소스명·YYYY-MM-DD"
            "scriptLines": [ "...", "...", "..." ],        // 화법 최대 3문장
            "checklist": [ "..." ],
            "generationStatus",          // LLM | TEMPLATE | REASON_ONLY
            "tagStatus", "rejectedReason",
            "weatherNote",               // 비·눈 예보 참고, 없으면 null
            "recommendedProducts": [ "..." ] }            // pipeline.toml product_mapping, 없으면 []
```

**태깅 / 되돌리기**

```
POST /api/recommendations/{id}/tag
Request:  { "tagStatus": "REJECTED", "rejectedReason": "NOT_TARGET" }
Response: { "recommendationId", "tagStatus", "rejectedReason" }

DELETE /api/recommendations/{id}/tag
Response: { "recommendationId", "tagStatus": "UNTAGGED", "rejectedReason": null }
```

- `tagStatus`: `VISITED`(방문함)/`HOLD`/`REJECTED`. `rejectedReason`: `ALREADY_CUSTOMER`/`NOT_TARGET`/`INFO_ERROR`/`UNREACHABLE` — `REJECTED`일 때만 정확히 1개 필수.
- 추천 1건당 태깅 1행이며 재태깅은 갱신, 되돌리기는 삭제다. 감사 로그에 `TAG_SAVED`/`TAG_REVERTED`(변경 전후 값)를 남긴다.

**임계치**

```
GET /api/thresholds
Response: [ { "id", "signalType", "category",   // SIGNAL | SYSTEM
              "label", "description", "thresholdValue", "unit",
              "isFixed", "integerOnly", "minValue", "maxValue",
              "updatedByName", "updatedAt" } ]

PUT /api/thresholds/{id}
Request:  { "thresholdValue": 12, "unit": "건" }   // unit 생략 가능, 주면 저장 단위와 비교
Response: 변경 후 항목(위와 같은 형식)

GET /api/thresholds/{id}/history
Response: [ { "id", "changedByName", "changedAt", "beforeValue", "afterValue" } ]
```

값이 실제로 바뀐 경우에만 저장·감사 로그(`THRESHOLD_UPDATED`)를 남기며, 다음 배치부터 적용된다(배치는 실행 시작 시 THRESHOLD_CONFIG를 읽는다). 이력은 감사 로그에서 조회한다.

**배치**

```
POST /api/batch/trigger
Response: { "run": BatchRunView, "alreadyRunning": false }

GET /api/batch/status
Response: { "latestRun": BatchRunView | null, "cooldownRemainingSeconds", "cooldownMinutes" }

BatchRunView = { "id", "runType",        // SCHEDULED | MANUAL
                 "status",               // RUNNING | SUCCESS | FAILED
                 "targetDate", "triggeredByName", "requestedAt", "startedAt",
                 "completedAt", "expectedCompletionAt", "failureReason" }
```

- 이미 `RUNNING`인 실행이 있으면 새로 만들지 않고 그 실행을 `alreadyRunning: true`로 돌려준다(RULE-SENSE-06).
- `expectedCompletionAt`은 `RUNNING`일 때만 채우며, 최근 실행 평균 소요시간(없으면 15분)으로 추정한다.
- 감사 로그 `BATCH_RUN_REQUESTED`, 완료 시 `BATCH_RUN_COMPLETED`.

**데이터 신선도**

```
GET /api/data-freshness
Response: { "referenceDate", "delayed", "maxDelayDays", "todaysListReady",
            "latestRunStatus", "message",
            "sources": [ { "sourceName", "displayName", "status",   // FRESH | FALLBACK | DEGRADED | UNAVAILABLE
                           "latestAsOfDate", "expectedAsOfDate", "delayDays", "isFallback" } ] }
```

- `delayed`는 `message`가 있을 때 `true`다. 메시지 우선순위: 오늘 배치 실패 → 수집 불가(UNAVAILABLE) 소스 → 정규화 미완료(DEGRADED) 소스 → 폴백 사용 → 성공했으나 오늘 명부 없음 → 07:30 이후 미완료.
- `SKIPPED` 소스는 목록에서 뺀다. `maxDelayDays`는 **폴백(FALLBACK)을 쓴 소스만** 센다 — 정상 수집인데 기준일이 늦은 공표 주기(환율 주말·인허가 D-2 등)는 지연으로 보지 않는다.

**CRM 등록 파일 다운로드**

```
GET /api/recommendations/export?date=2026-10-14&format=csv     // format = csv | xlsx, 기본 csv
Content-Disposition: attachment; filename*=UTF-8''cmaker_{지점코드}_{date}.{ext}
```

- 파일명 규칙: `cmaker_{branch_code}_{YYYY-MM-DD}.{csv|xlsx}` (지점코드가 없으면 지점 ID).
- 포함 행: 그날 명부 중 **'방문함'(VISITED)으로 태깅했고 영업상태가 '정상'인 건만**.
- 컬럼: 사내 CRM [02220] 고객관리 등록 항목 순서의 **10개 컬럼**(사업자등록번호는 공란, 상세유형·추진상품은 `product_mapping`). 컬럼별 값 세부는 `docs/crm-integration.md` §3 참조.
- CSV는 `utf-8-sig`(Excel 호환 BOM), media type `text/csv; charset=utf-8`. XLSX는 openpyxl, 시트명 **'접촉명부'**.
- 스프레드시트 수식 주입 방지: `=`, `+`, `-`, `@`, 탭, CR로 시작하는 셀 값 앞에 `'`를 붙인다.
- 다운로드마다 감사 로그 `CRM_EXPORT`(형식·행 수)를 남긴다.

---

## 7. DB 스키마

`backend/database/schema.sql` 단일 파일 관리 (OPS-09). 모든 객체는 `cmaker` 스키마에 생성된다(§4). 컬럼·제약 세부와 ERD 대비 변경점(USER → `app_user`, `audit_log` 신설 등)은 `6-erd.md`와 `schema.sql` 헤더 주석을 참조한다. 모든 DDL이 `IF NOT EXISTS`라 재실행해도 기존 데이터는 유지된다.

### 7.1 테이블 생성 순서

`schema.sql`의 실제 생성 순서다(FK 참조 순서). `batch_run`은 ERD 순서상 뒤쪽이지만 `event`·`signal`·`recommendation`이 실행 ID를 참조하므로 5번째로 만든다.

```
1. branch
2. branch_history          → branch
3. app_user                → branch                (ERD의 USER, 예약어 회피)
4. data_source_snapshot
5. batch_run               → app_user
6. event                   → branch, batch_run
7. business
8. signal                  → data_source_snapshot, branch, business, event, batch_run
9. recommendation          → branch, business, batch_run
10. recommendation_event   → recommendation, event
11. brief                  → recommendation
12. tag_feedback           → recommendation, app_user
13. signal_weight
14. threshold_config       → app_user
15. audit_log              → app_user
```

### 7.2 트리거 (CONST-19)

`trg_branch_effective_from` (BEFORE INSERT OR UPDATE ON branch) → 함수 `branch_apply_effective_from()`:
- INSERT: `effective_from`을 다음 날 07:30(KST)으로 설정
- UPDATE: 추적 대상 값(이름·주소·좌표·반경·주력업종·외환·ATM 수)이 바뀌면 옛 값을 `branch_history`로 옮기고 `effective_from`을 다음 날 07:30으로 설정. 값이 그대로면 `effective_from`을 수동으로 바꾸지 못하게 기존 값으로 고정
- 함수에 `SET search_path = cmaker, pg_temp`가 걸려 있어 호출 세션의 search_path와 무관하게 `cmaker.branch_history`에 기록된다

### 7.3 인덱스 (15개)

```
idx_branch_history_branch        ON branch_history(branch_id, valid_until)
idx_snapshot_source_date         ON data_source_snapshot(source_name, as_of_date DESC, id DESC)
idx_batch_run_status             ON batch_run(status)
idx_batch_run_requested          ON batch_run(triggered_by, requested_at DESC)
uq_batch_run_single_running      UNIQUE ON batch_run(status) WHERE status = 'RUNNING'   -- CONST-17
idx_event_branch_date            ON event(branch_id, occurred_on)
idx_event_cooldown               ON event(branch_id, signal_type, target_key, occurred_on DESC)
idx_business_status              ON business(operating_status)
idx_business_lat_lng             ON business(lat, lng)
idx_signal_branch_date           ON signal(branch_id, as_of_date)
idx_signal_event                 ON signal(event_id)
idx_recommendation_branch_date   ON recommendation(branch_id, recommended_on)
idx_recommendation_business      ON recommendation(business_id, recommended_on DESC)
idx_tag_feedback_recommendation  ON tag_feedback(recommendation_id)
idx_audit_log_entity             ON audit_log(entity_type, entity_id, created_at DESC)
```

이 외에 UNIQUE 제약(예: `branch.branch_code`, `app_user.username`, `recommendation(branch_id, recommended_on, rank_in_branch)`)이 만드는 인덱스가 있다.

### 7.4 초기 데이터 (`seed.sql`, psql 직접 실행)

파일럿 지점 온보딩 시 `backend/database/seed.sql`로 다음 4가지를 투입한다. 지점·계정 값은 예시이므로 실제 파일럿 값으로 바꿔 실행한다.

| 테이블 | 투입 방법 | 비고 |
|---|---|---|
| BRANCH | `seed.sql` INSERT | UC-01/02 화면 없음, 운영자 직접 입력. 좌표는 `geocode_job`이 채운다 |
| USER (`app_user`) | `seed.sql` INSERT | 계정 생성 화면 없음. RM·지점장은 소속 지점 필수, 본부는 NULL(CONST-03) |
| THRESHOLD_CONFIG | `seed.sql` INSERT | SIGNAL 10행 + SYSTEM 5행(`EVENT_COOLDOWN_DAYS`, `DAILY_EVENT_CAP`=12, `SIGNAL_SHARE_CAP_PCT`=30, `CONTACT_COOLDOWN_DAYS`, `AREA_REASON_RATIO_LIMIT`). 없으면 배치 판정 동작 안 함 |
| SIGNAL_WEIGHT | `seed.sql` INSERT | 신호 10종 초기 가중치 w₀(`industry_code='*'`). MVP는 학습 갱신 비활성 |

**초기 비밀번호는 psql 변수로 넘긴다(필수).** 저장소에 비밀번호를 남기지 않기 위해서이며, 변수가 없으면 `seed.sql`이 안내 메시지를 출력하고 아무것도 넣지 않고 종료한다.

```bash
psql -U myapp_user -d myapp_db -v initial_password='<초기 비밀번호>' -f backend/database/seed.sql
```

모든 INSERT가 `ON CONFLICT ... DO NOTHING`이라 재실행해도 기존 행을 덮어쓰지 않는다.

**기존 운영 DB(2026-10-13 이전에 seed를 적용한 DB)**는 아래 패치를 적용한다. 테이블 구조 변경은 없고 여러 번 실행해도 안전하다. 예보 신호 4종 임계치와 `SIGNAL_SHARE_CAP_PCT` 행, 예보 신호 가중치를 추가하고, `DAILY_EVENT_CAP`이 8이면 12로 바꾸며 감사 로그를 남긴다(본부가 이미 다른 값으로 바꿨다면 건드리지 않는다).

```bash
psql -U myapp_user -d myapp_db -v ON_ERROR_STOP=1 -f backend/database/patches/2026-10-13_forecast_signals.sql
```

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
  └─ openai.OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=10, max_retries=1)
     └─ client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{system}, {user}],
            max_tokens=BriefingConfig.max_output_tokens,   # 400
            extra_body={"thinking": {"type": "disabled"}},
        )
```

**결정론 부분과 LLM 부분의 분리.** 브리프 중 LLM이 쓰는 것은 **전화 화법(`talk_script`)뿐**이다. 나머지는 판단 레이어가 결정론적으로 만든다.

| 브리프 항목 | 생성 주체 |
|---|---|
| 사실 문장(`reasonFacts`, 출처 태그 포함)·명부 1줄 요약(`reasonSummary`) | `briefing/fact_builder.py` — 신호 종류별 고정 문구 + 신호 원장 수치 |
| 화법의 연락 사유·목적(`call_reason`/`call_purpose`) | `fact_builder.py` — 기여도 1위 신호 종류로 결정 (새 사실을 담지 않음) |
| 체크리스트 | `pipeline.toml` `[briefing] default_checklist` 그대로 |
| 날씨 참고(`weatherNote`) | `forecast_normalizer.weather_note()` — 비·눈 예보, 날씨 영향 업종만. 순위·근거·화법에는 쓰지 않음 |
| 추천상품(`recommendedProducts`) | `pipeline.toml` `[product_mapping]` (대표 신호 → 상품). 화법에는 넣지 않음 |
| 화법(`scriptLines`) | LLM (또는 TEMPLATE) → `citation_guard` 검증 |

확정된 RECOMMENDATION의 사실 문장과 `org_name`·`branch_name`·`business_name`·`industry`·`call_reason`·`call_purpose`만 user 메시지(JSON)에 넣어 Chat Completion으로 생성한다.
응답 전체는 설명·마크다운 fence 없는 `{"script": ["문장1", ...]}` strict JSON 객체여야 하며, 실제 LLM 경로는 비어 있지 않은 `list[str]`만 허용한다
(실측: 실제 프롬프트로 216 completion tokens, 유효 JSON 반환 확인). 프롬프트 버전은 **`brief-v5`**(`brief_generator.py`의 `PROMPT_VERSION`)이며,
저장되는 prompt의 첫 줄(`[brief-v5]`)과 배치 run manifest의 `prompt_version`에 기록한다.

**화법 3문장 구조** (시스템 프롬프트):
1. 인사·연락 사유 — 기관명(`greeting_org_name`, NH농협은행)·지점명을 밝히고, `call_reason`과 사실의 핵심 변화로 왜 지금 연락했는지
2. 연락 목적 — `call_purpose`를 바탕으로 사업장 입장에서 지점이 무엇을 도우려는지
3. 다음 행동 요청 — 방문 또는 짧은 상담 일정을 정중하게 여쭙기

프롬프트는 상품명·대출·금리 등 권유 금지, 수치는 사실 그대로, 예보는 "예보되어"처럼 예보임을 밝히기, 원소당 정확히 한 문장을 지시한다. LLM 응답의 첫 문장은 `polish_greeting()`이 "{기관} {지점}입니다, " → "{기관} {지점}에서 "로만 다듬는다(사실·수치는 바꾸지 않음).

**`generation_status` 3종**

| 상태 | 조건 |
|---|---|
| `LLM` | 게이트웨이 응답이 strict JSON이고 citation guard를 통과한 문장이 1개 이상 |
| `TEMPLATE` | LLM 미설정(`LLM_BASE_URL`/`LLM_API_KEY` 비어 있음)·장애·형식 오류 시 정형 화법 사용. 정형 화법도 같은 3문장 구조로 `call_reason`/`call_purpose`와 고정 문구 "편하신 시간에 담당 직원이 잠시 찾아뵙고 …"를 쓴다 |
| `REASON_ONLY` | 검증에서 화법이 전부 차단되어 사유만 표시(RULE-BRIEF-02) |

빈 응답·타임아웃·HTTP 오류뿐 아니라 HTTP 200이어도 OpenAI 호환 응답이 malformed/non-JSON이면
`LlmUnavailableError`로 통일해 `TEMPLATE` 정형 화법으로 대체한다. 예외 원문에는 Virtual Key 식별자가
포함될 수 있으므로 저장하지 않고, 비식별화된 예외 클래스명만 검증 오류에 기록한다.

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

- 프롬프트에 "facts·call_reason·call_purpose에 있는 내용만 언급, 그 밖의 사실·수치·날짜·혜택을 만들지 마라" 지시
- `backend/batch/briefing/citation_guard.py`가 결정론적 후처리 검증을 한다. 차단 목록은 `pipeline.toml` `[briefing]`에 있다.

**사실 문장 검사** (`validate_facts`, 문장 단위로 제거)
1. 본문이 비었거나 출처 태그가 `소스명·YYYY-MM-DD` 형식이 아니면 제거
2. 금칙 표현(`forbidden_expressions`) 포함 시 제거

**화법 문장 검사** (`validate_script`, 문장 분리 후 아래 순서로 먼저 걸린 사유 하나로 차단)
1. 대괄호(`[...]`) 구간 제거, 빈 문장 건너뜀
2. 금칙 표현(`forbidden_expressions`, RULE-BRIEF-03: 확정 수익·원금 보장 등)
3. **예보 단정 표현**(`assertive_forecast_expressions`: "추워집니다", "비가 옵니다" 등) — 예보는 "예보되어"처럼만 말한다. 화법에서만 차단한다
4. **상품어**(`product_terms`: 대출·예금·금리·한도·통장·카드·여신·상품·혜택·수수료 등) — MVP에는 상품설명서 RAG가 없어 인용을 붙일 수 없으므로 차단(CLAUDE.md §0.8)
5. **근거 없는 수치** — 사실 문장·지점명·상호·연락 사유/목적에 없는 수치·날짜(부호 없는 크기 표현은 허용)

- 표현 비교는 공백을 제거한 문자열로 한다. 수치 표기 차이(Unicode 부호·쉼표·소수 끝 0)는 `Decimal`로 정규화해 비교한다.
- 통과 문장이 `max_script_sentences`(3)를 초과하면 사실의 수치·핵심 토큰과 연관된 문장을 우선 보존한 뒤 원래 순서를 유지한다.
- 차단 사유는 `brief.validation_errors`에 남는다.

---

## 9. 프론트엔드 연동

서비스 표시명은 **NH Campaigner**다(`frontend/index.html`의 `<title>`, CRM 등록 파일 `내용` 접두어 `[NH Campaigner]`). 저장소·배포 경로·DB 스키마 등 내부 명칭은 계속 `c-maker`/`cmaker`를 쓴다(§18). 색상·버튼·라운드 등 시각 규칙은 `9-style-guide.md`를 따른다(토큰: `src/styles/tokens.css`).

### 9.1 현재 구현 상태 (2026-10-14, `frontend/src` 기준)

모든 API 클라이언트가 `api/client.ts`의 `apiFetch`/`apiDownload`로 실제 백엔드를 호출한다. mock 데이터는 남아 있지 않다.

| 구분 | 파일 |
|---|---|
| Pages | `LoginPage`, `DashboardPage`, `BriefDetailPage`, `AdminThresholdPage`, `PendingPage` |
| Components — common | `Layout`, `TopUtilityBar`, `BrandSignature`, `Button`, `Banner`, `DataDelayBanner`, `DataFreshnessStamps`, `SourceStamp`, `StatusBadge`, `Tabs`, `ConfirmDialog`, `ManualBatchTrigger` |
| Components — recommendation | `RecommendationList`, `RecommendationCard`, `TagButtons`, `TagStatusBadge`, `TagUndoToast`, `CrmDownloadButton`, `SignalBarsPanel`, `TodayRecordPanel` |
| Components — brief | `BriefDetail` |
| Components — admin | `ThresholdEditor`, `ThresholdHistoryPanel` |
| API (`api/*.api.ts`) | `client.ts`, `auth.api.ts`(login·refresh), `recommendation.api.ts`(목록·요약·export), `brief.api.ts`, `tag.api.ts`(POST·DELETE), `threshold.api.ts`, `batch.api.ts`(trigger·status·data-freshness) |
| Queries | `useAuth`, `useRecommendations`, `useBrief`, `useTagMutation`, `useTagWithUndo`, `useCrmExport`, `useThresholds`, `useTriggerBatch`, `useBatchRunStatus` |
| Stores (Zustand) | `authStore`, `filterStore` |
| Types | `auth.ts`, `recommendation.ts`, `brief.ts`, `batchRun.ts`, `threshold.ts` |
| Utils | `date.ts`, `industry.ts`, `roles.ts`, `signal.ts`, `sourceTag.ts` |

### 9.2 라우팅·인증 연동 (완료)

| 경로 | 화면 | 접근 역할 |
|---|---|---|
| `/login` | LoginPage | 전체 |
| `/dashboard` | DashboardPage | RM, BRANCH_MANAGER |
| `/brief/:id` | BriefDetailPage | RM, BRANCH_MANAGER |
| `/admin/thresholds` | AdminThresholdPage | HQ_MARKETING |
| `/pending` | PendingPage (본부 준법 안내 — 캠페인 승인은 Phase 3) | HQ_COMPLIANCE |

- `router.tsx`의 `RequireRole`이 역할별 화면 접근을 막지만 UX용이며, 최종 권한 검증은 API 서버가 한다(§6.1).
- `App.tsx`가 `registerTokenGetter(getStoredToken)`로 모든 요청에 JWT를 싣고, `registerUnauthorizedHandler`로 401 시 로그아웃한다.

### 9.3 mock 교체·신규 작업

v2.2.0에 남아 있던 mock → `apiFetch` 교체, `mockData.ts` 삭제, `batchRun.ts`·`batch.api.ts`·`useTriggerBatch`·`useBatchRunStatus`·`ManualBatchTrigger` 신규, `UserRole`에 `HQ_MARKETING`/`HQ_COMPLIANCE` 추가, `registerTokenGetter` 호출 추가는 **모두 완료**됐다.

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
  ├─ 사전 확인: 효력 지점·좌표 보유 효력 지점이 0건이면 외부 호출 전 실패
  │
  ├─ connectors: 소스별 수집 + DATA_SOURCE_SNAPSHOT 적재
  │   PERMIT_DAILY · KMA_WARNING · KMA_FORECAST · ECOS_FX · OPINET_PRICE (+ KMA_NOWCAST 관측 축적)
  │   (장애 시 → 소스별 최대 허용 나이 안의 최신 snapshot, 초과 시 UNAVAILABLE)
  │
  ├─ PERMIT/NTS 후처리 → normalizers: SIGNAL 정규화 + scope 태깅 (예보 신호는 forecast_normalizer)
  │
  ├─ sensing: 임계치 판정 → EVENT 승격
  │   쿨다운(EVENT_COOLDOWN_DAYS 14일) / 지점당 일일 상한(DAILY_EVENT_CAP 12건) / 병합 처리
  │
  ├─ targeting: 짧은 read planning transaction에서 배제·스코어링·TOP 20 확정
  │   배제: 영업상태 → 방문함 쿨다운 → 부적합 사유별 기간 → 수신거부(접촉 불가)
  │   Score = (Σᵢ wᵢ·sᵢ·aᵢ + R) × 근접도 × 규모적합도
  │   명부 다양성 상한: 신호별(SIGNAL_SHARE_CAP_PCT 30%) + 같은 건물(same_address_cap 2곳)
  │   탐색 슬롯 3건 (톰슨 샘플링) — 구조만 구현, exploration_enabled=false (Phase 2 가동)
  │
  ├─ briefing: DB transaction 밖에서 LiteLLM Gateway 호출 (LLM_MAX_CONCURRENCY 병렬)
  │
  └─ publish: 짧은 transaction에서 RECOMMENDATION + BRIEF 원자 적재 및 1:1 검증

07:30 이전 완료 (P95 SLA)
```

**connectors — PERMIT_DAILY (인허가 변동분)**: 행안부 **업종별 인허가 조회 API**를 쓴다. 호출 URL은 `https://apis.data.go.kr/1741000/{업종 path}/info`이며 전 업종을 한 번에 받는 API는 없다. `pipeline.toml` `[[sources.PERMIT_DAILY.options.services]]`에 9개 업종이 있고 그중 **통신판매업은 `enabled = false`**(신고 주소가 자택·공유오피스인 경우가 많아 반경 매칭 신뢰도가 낮음)라 8개 업종을 호출한다. 기준일은 **D-2**(`expected_lag_days = 2`), 변동분 창은 `LAST_MDFCN_PNT` 기준 `[from, 기준일 00:00)`, `from = min(기준일 − (expected_lag_days + overlap_days), 직전 성공 창의 to − expected_lag_days)`이며 `max_lookback_days`(7일)보다 과거로는 가지 않는다, 지자체 필터는 `region_codes`(`OPN_ATMY_GRP_CD`)다. 한 업종이라도 실패하면 소스 전체를 실패로 본다. 요청 파라미터·응답 필드 세부는 `api/11-api-spec.md`, 설정값은 `backend/config/pipeline.toml`을 참조한다.

**인허가 적재 시 보건소류 제외**: 업태구분명에 `excluded_permit_keywords`(보건소·보건지소·보건진료소·보건의료원)가 포함되거나 사업장명이 그 키워드로 끝나면 BUSINESS에 넣지 않고 개업 신호도 만들지 않는다(`permit_parser.is_excluded_permit`, 일간 변동분과 월간 전수 모두 적용).

**targeting 세부**
- **Score** (`targeting/scorer.py` 상단 docstring·구현): `Score = (Σᵢ wᵢ·sᵢ·aᵢ + R) × 근접도 × 규모적합도`. wᵢ는 SIGNAL_WEIGHT(표본 30건 미만 조합은 `'*'` 가중치 상속), sᵢ는 이벤트 최신 신호 강도(0~1), **aᵢ는 적용도**(사업체 신호는 해당 사업체만 1, 업종명이 있는 업종 신호는 같은 업종만 1, 그 밖의 업종·상권·거시 신호는 업종×신호 적합도 `industry_signal_fit`), R은 신선도 항(인허가 경과일 감쇠·최근 미노출·업종×당일신호 적합도 가중합, 0~1). 근접도는 지점 위치 1.0 → 담당 반경 경계 0.5(선형), 규모적합도는 지점 주력업종 일치 시 1.2, 아니면 1.0. 예보 이벤트는 예보 대상일(`valid_until`)이 지나면 사유로 쓰지 않는다. 환율·유가·기상특보(`[scoring] superseded_signal_types`)는 같은 `target_key`에 더 새로운 기준일의 신호가 있으면(임계치 미달 포함, `repo.load_latest_signal_dates` → `scorer.is_superseded`) 사유로 쓰지 않고, 건수는 `superseded_events` 통계에 남긴다.
- **상호 없음 배제** (`INVALID_NAME`, 영업상태 다음 순서): 공백을 지운 상호가 `[exclusion] invalid_business_name_prefixes`(`업소명없음`)로 시작하거나, `exclude_industry_named_business = true`일 때 상호가 업종 분류명(`·`로 나눈 대·중·소분류) 중 하나와 같으면 명부에서 뺀다. BUSINESS 적재는 그대로 둔다.
- **부적합 사유별 배제 기간** (`pipeline.toml` `[exclusion.reject_exclusion_days]`, 0 = 영구): `INFO_ERROR`(정보 오류) **90일**, `ALREADY_CUSTOMER`·`NOT_TARGET`·`UNREACHABLE`은 **영구**. `UNREACHABLE`(접촉 불가)은 수신거부로 취급한다. 방문함 태깅은 `CONTACT_COOLDOWN_DAYS`(기본 30일) 동안 배제한다.
- **신호별 명부 상한**: 주 사유(기여도 1위)가 `signal_share_capped_types` 7종(`FX_DAILY_CHANGE`, `OIL_PRICE_CHANGE`, `WEATHER_WARNING`, `TEMP_SHIFT_FORECAST`, `SEASON_SHIFT_FORECAST`, `FIRST_FREEZE_FORECAST`, `FIRST_HEAT_FORECAST`)인 추천은 한 종류당 `top_n × SIGNAL_SHARE_CAP_PCT`(기본 30% → 6건)까지만 싣고, 넘치는 자리는 다음 순위 후보로 채운다. 다른 후보로 20건을 못 채우면 미룬 후보로 채운다. 사업장 단위 신호는 대상이 아니다.
- **같은 건물 상한**: `same_address_cap = 2` — 도로명주소의 **쉼표 앞**(괄호 참고항목 제거, 공백 정리)이 같은 사업장은 2곳까지만 싣는다. 넘친 후보는 명부에서 빼고 다음 순위로 채우며, **후보가 모자라면 `top_n` 미만도 허용**한다. 주소가 없으면 상한 대상이 아니다.
- 두 상한은 `exploration.apply_signal_share_cap()`이 함께 적용하고, 밀려난 건수는 통계에만 남긴다(`run_daily.py`).
- **탐색 슬롯**: `assemble_recommendations()`에 톰슨 샘플링 구조(시드 = 지점·일자)가 있으나 `pipeline.toml` `exploration_enabled = false`라 MVP에서는 3자리도 점수순 일반 후보로 채운다. 가동은 Phase 2.

- 폴백 최대 나이는 `PERMIT_DAILY=3일`, `NTS_STATUS=1일`, `KMA_WARNING=1일`, `KMA_FORECAST=1일`, `ECOS_FX=7일`, `OPINET_PRICE=2일`이다(`KMA_NOWCAST`는 소스 상태에 넣지 않는 관측 축적 스냅샷). 2026-10-13 예보 신호 추가 시 운영 DB에는 `backend/database/patches/2026-10-13_forecast_signals.sql`을 적용한다. 새 수집이 성공한 `FRESH`도 기대 기준일보다 오래되면 `delay_days`로 지연을 노출한다.
- PERMIT/NTS 후처리는 각각 격리한다. 실패한 소스는 `UNAVAILABLE`로 낮추고 다른 처리를 계속한다. normalizer도 소스별로 격리하지만 실패 소스는 `DEGRADED`, 해당 지점은 실패로 기록되어 최종 배치는 `FAILED`가 된다.
- 반복 이벤트의 cooldown은 최초 `occurred_on`이 아니라 `last_merged_on`을 포함한 최근 병합 활동일을 기준으로 계산한다.
- 브리프 생성 또는 추천·브리프 1:1 검증이 최종 실패하면 publish transaction을 rollback해 기존 당일 명부를 보존한다.

### 10.2 월간 모집단 배치 (`run_monthly.py`)

**SBIZ**는 페이지별 `totalCount` 일관성, `bizesId` 중복 없음, 전수 수집을 확인한 `complete=true` manifest만 허용한다. 모든 좌표 지점의 snapshot을 먼저 보존한 뒤 전역 `bizesId` 합집합을 만들고, 단일 transaction에서 upsert와 전역 누락 폐업 판정을 각각 한 번 수행한다. `NO_DATA`, 0건, invalid manifest/레코드/설정, 한 지점이라도 수집·snapshot 실패, 기존 정상 모집단 대비 **50% 초과** 감소는 fail-closed로 BUSINESS publish를 시작하지 않거나 전체 rollback한다(50% 이하는 허용).

```toml
min_population_records = 1
max_population_drop_ratio = 0.5
```

**PERMIT_FULL**은 각 CSV를 SHA-256 기반 content-addressed 불변 archive에 원자 보관하고, inbox 원본이 아니라 그 archive를 실제 parse 입력으로 사용한다. 모든 파일의 BUSINESS 반영은 단일 transaction이므로 한 파일의 parse/DB 실패도 전체 PERMIT publish를 rollback한다. `PERMIT_FULL_DATA_DIR`가 설정됐는데 CSV가 0개면 실패하며, 미설정이면 승인 전 기존 정책대로 skip하고 `publish_complete=false`를 남긴다.

### 10.3 수동 재실행 (REQ-17)

API 서버의 `batch_service.py`가 `subprocess.Popen`으로 `run_daily.py`를 별도 프로세스로 기동하고 즉시 응답한다. daemon worker watcher는 자식 종료를 회수하고, 자식이 완료 상태를 남기지 않은 채 종료하면 아직 `RUNNING`인 수동 실행만 `FAILED`로 바꾸며 완료 감사를 같은 transaction에 남긴다. 완료 갱신은 `status='RUNNING'` 조건의 fencing으로 이미 확정된 terminal 상태를 덮어쓰지 않는다.

상태 조회와 수동 실행 요청의 stale 정리는 일간·월간 공용 lock을 획득해 worker 부재를 확인한 경우에만 수행한다. lock이 busy면 수동 요청은 `BATCH_RUNNING`을 반환한다. 프론트엔드는 `BATCH_RUN` 상태를 폴링해 완료를 감지한다.

### 10.4 cron 스케줄

일간과 월간은 실행 전체에 같은 **PostgreSQL session advisory lock**을 사용해 데이터 변경을 직렬화하고, 지오코딩은 별도 lock을 사용한다. 공용 lock이 busy면 예약 일간·월간은 실제 처리를 시작하지 않고 종료한다. 예약 일간의 stale 정리도 공용 lock 획득 후에만 수행한다.

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

> [!WARNING]
> **알려진 운영 residual**
> - 월간 배치가 06:00까지 공용 lock을 점유하면 예약 일간은 자동 재시도 없이 종료된다. 월간 완료 후 일간을 수동 재실행한다.
> - `PERMIT_FULL_DATA_DIR` 미설정 시 월간은 해당 소스를 skip하고 `publish_complete=false`로 정상 종료할 수 있다.
> - 태그 갱신이 동시에 경합하면 한 요청이 실패할 수 있으므로 클라이언트가 상태를 다시 조회해야 한다.

리다이렉트 대상이 `cron-*.log`인 이유는 §10.5를 참고한다. `LOG_DIR`이 설정되면 배치가 직접 `daily.log`·`monthly.log`·`geocode.log`에 쓰기 때문에, cron 리다이렉트를 같은 이름으로 두면 한 파일에 두 경로가 섞인다.

**등록 확인**

```bash
sudo journalctl -u cron --since '-15min' | grep CMD    # 실행 이력
tail -5 /var/log/c-maker/geocode.log                   # 10분 주기 잡이 가장 먼저 찍힌다
```

### 10.5 배치 로그

Python `logging` 모듈로 구조화 로그 (OPS-08):
- 기록 항목: 단계별 처리 건수, 소요시간, 실패 소스명
- 예약 일간의 07:30 SLA 판정은 `BATCH_RUN.stage_stats.sla`에 `applicable`, `deadline`, `finished_at`, `met`, `missed_by_seconds`로 저장하며, 미달 시 `SLA_MISSED` ERROR 로그를 남긴다. 수동 실행은 `applicable=false`다.
- 타임스탬프는 `log_setup.py`가 **UTC로 고정**해 찍는다(`datetime.fromtimestamp(record.created, UTC)`). 서버 타임존을 KST로 바꿔도 로그의 `ts`는 `+00:00`을 유지하므로 과거 로그와 형식이 섞이지 않는다.

`.env`의 `LOG_DIR` 설정에 따라 출력 위치가 갈린다.

| `LOG_DIR` | 출력 |
|---|---|
| 설정됨 (예: `/var/log/c-maker`) | `<LOG_DIR>/<name>.log`에 **파일로만** 쓴다 — `daily.log`, `monthly.log`, `geocode.log`, `api.log` |
| 비어 있음 | stdout (cron 리다이렉트·journald가 수집) |

> `LOG_DIR`이 설정된 상태에서는 배치가 이미 `daily.log`에 직접 쓰므로, cron 리다이렉트는 **다른 이름**(`cron-daily.log`)으로 둔다(§10.4). 같은 이름을 쓰면 한 파일에 두 경로가 섞인다. `cron-*.log`에는 정상 동작 시 아무것도 남지 않고, 파이썬이 뜨기 전에 죽는 경우(경로 오류, venv 누락 등)의 stderr만 잡힌다.

```bash
sudo mkdir -p /var/log/c-maker
sudo chown ubuntu:ubuntu /var/log/c-maker
```

---

## 11. 백엔드 외부 호출 3경로

| 경로 | 호출 주체 | 프로토콜 | 인증 | 용도 | 장애 대응 |
|---|---|---|---|---|---|
| **공공데이터 API** | 배치 connectors | HTTPS (443) | API Key (.env) | 신호 수집, 모집단 적재, 사업자 검증 | 일간은 소스별 최대 허용 나이 내 snapshot 폴백, 월간은 완전성 검증 실패 시 fail-closed |
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

저장소 기준 파일 `deploy/c-maker-api.service`와 같은 내용이다.

```ini
# /etc/systemd/system/c-maker-api.service  (docs/10-implementation-guide.md §12.1)
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
# 수동 재실행(REQ-17)으로 기동한 run_daily.py 자식 프로세스가 API 재시작 때 함께 종료되지 않도록
# 메인 프로세스만 종료 신호를 받게 한다. 비정상 종료된 실행은 batch_stale_minutes 경과 후 FAILED 처리된다.
KillMode=process

[Install]
WantedBy=multi-user.target
```

**`KillMode=process`를 쓰는 이유**: 기본값(`control-group`)이면 `systemctl restart c-maker-api` 때 같은 cgroup에 있는 수동 재실행 배치(`batch_service.py`가 `subprocess.Popen`으로 띄운 `run_daily.py`)까지 함께 종료된다. `process`로 두면 uvicorn 메인 프로세스만 종료 신호를 받아 진행 중인 배치가 끝까지 돈다. 그래도 배치가 비정상 종료돼 `RUNNING`으로 남으면 `BATCH_STALE_MINUTES`(기본 180분) 경과 후 상태 조회·수동 요청·예약 일간 실행 시 `FAILED`로 정리된다(§10.3·§10.4).

### 12.2 프론트엔드 (`c-maker-frontend.service`)

> **참고**: nvm 환경에서 `npm install -g serve`로 설치하면 serve 바이너리가 `/usr/bin/serve`가 아닌 nvm 경로에 위치할 수 있다. 아래 명령으로 실제 경로를 확인한 뒤 `ExecStart`를 맞춘다. systemd는 로그인 셸의 PATH를 사용하지 않고, serve는 `#!/usr/bin/env node`로 실행되므로 nvm의 node 경로를 `Environment=PATH=...`에 명시해야 한다.
> ```bash
> which serve   # 예: /home/ubuntu/.nvm/versions/node/v24.21.0/bin/serve
> ```

```ini
[Unit]
Description=C-MAKER Frontend (serve)
After=network.target

[Service]
User=ubuntu
# serve는 `#!/usr/bin/env node`로 실행되므로 nvm의 node가 PATH에 있어야 한다(systemd는 셸 PATH를 쓰지 않음)
Environment=PATH=/home/ubuntu/.nvm/versions/node/v24.21.0/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/ubuntu/.nvm/versions/node/v24.21.0/bin/serve -s /home/ubuntu/c-maker/frontend/dist -l tcp://127.0.0.1:8080
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
cp .env.example .env    # 값 채우기(§3). JWT_SECRET이 비었거나 32자 미만이면 API가 기동하지 않는다

# 3) DB 스키마 적용 (기존 myapp_db / myapp_user 사용, 테이블은 cmaker 스키마에 생성)
psql -U myapp_user -d myapp_db -f backend/database/schema.sql
psql -U myapp_user -d myapp_db -c "\dt cmaker.*"   # 15개 테이블 생성 확인

# 4) 초기 데이터 (BRANCH + USER + THRESHOLD_CONFIG + SIGNAL_WEIGHT) — initial_password 필수
psql -U myapp_user -d myapp_db -v initial_password='<초기 비밀번호>' -f backend/database/seed.sql

# 4-1) 패치 — 2026-10-13 이전 seed를 적용한 기존 DB만 (신규 DB는 seed에 포함돼 있어 불필요, 재실행해도 안전)
psql -U myapp_user -d myapp_db -v ON_ERROR_STOP=1 -f backend/database/patches/2026-10-13_forecast_signals.sql
# 4-2) 패치 — 2026-10-14 이전에 인허가 일간 배치를 돌린 기존 DB만 (약국·체력단련장업 관리번호 접두어 교체, 재실행해도 안전)
psql -U myapp_user -d myapp_db -v ON_ERROR_STOP=1 -f backend/database/patches/2026-10-14_permit_service_ids.sql

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
sudo install -o root -g root -m 644 deploy/c-maker.cron /etc/cron.d/c-maker
sudo systemctl restart cron

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

`7-execution-plan.md` v1.4.0 기준, EC2 배포 환경에 맞게 재정리한 **당초 계획(이력)**이다. 실제 구현 현황은 `7-execution-plan.md` v1.5.0 §2.1을 본다 — 지하철·재난문자 커넥터는 미구현이고, mock 교체는 완료됐다(§9.3).

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
| CRM 등록 파일 API | UC-08 (CSV/XLSX) |
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
| lint | 백엔드 ruff, 프론트엔드 ESLint(`npm run lint`) | mypy는 `requirements-dev.txt`에 없어 현재 설치·실행되지 않는다(도입 시 별도 추가) |

### 15.1 실행 방법

테스트·lint 의존성은 `backend/requirements-dev.txt`에 분리돼 있다(운영 실행에는 불필요). 설정은 저장소 루트 `pyproject.toml`의 `[tool.pytest.ini_options]`·`[tool.ruff]`를 따른다.

```bash
cd /home/ubuntu/c-maker
source .venv/bin/activate
pip install -r backend/requirements-dev.txt   # -r requirements.txt를 자체 포함한다

python -m pytest          # testpaths=backend/tests, addopts=-q
python -m ruff check backend
```

> **배포 시 누락 주의.** §13의 초기 배포 절차는 `requirements.txt`만 설치하므로, EC2 venv에 pytest·ruff가 들어가지 않는다. 실제로 2026-09-30까지 EC2에서 테스트가 한 번도 실행되지 않은 상태였다(`No module named pytest`). 서버에서 검증을 돌릴 계획이면 `requirements-dev.txt`도 설치한다.

> 1~3순위 테스트는 DB·외부 API를 쓰지 않는 순수 단위 테스트다. 운영 DB에 붙은 서버에서도 안전하게 돌릴 수 있다.

**마지막 확인 결과 (2026-09-30, EC2 Python 3.14.4 / pytest 9.1.1 / ruff 0.16.9)**

```
174 passed, 1 warning         # python -m pytest        (exit 0)
All checks passed!            # ruff check backend      (exit 0)
```

> **2026-10-14 재실행 미완료.** 문서 현행화 작업 환경(Windows 개발 PC)에 저장소 루트 `.venv`와 Python 인터프리터가 없어 `.venv\Scripts\python.exe -m pytest -q`를 실행하지 못했다. 위 수치는 `test_forecast.py`·`test_permit_connector.py` 추가 **이전** 결과이므로, 현재 테스트 수와 통과 여부는 EC2 또는 venv가 있는 환경에서 다시 실행해 갱신해야 한다.

`backend/tests/` (2026-10-14 기준 10개 테스트 파일 + `factories.py`)

| 테스트 파일 | 검증 대상 |
|---|---|
| `test_event_promoter.py` | 이벤트 승격 판정, 지점당 일일 상한 (RULE-SENSE-01/02) |
| `test_targeting.py` | 배제·스코어링 (RULE-TARGET-01/02) |
| `test_briefing.py` | 브리프 그라운딩·금칙 표현 (RULE-BRIEF-02/03) |
| `test_normalizers.py` | 신호 정규화 |
| `test_forecast.py` | 기상청 격자 변환, 예보 신호 4종 판정·시즌, 예보 이벤트 만료, 날씨 참고, 예보 사실 문장, 예보 단정 표현 차단, 신호별 명부 상한·같은 건물 상한 |
| `test_permit_connector.py` | 업종별 인허가 API 파라미터·페이징·totalCount, 업종별 중복 제거, resultCode, 비활성 업종 skip, 행 파싱·영업상태 매핑, 보건소류 제외, 변동분 창 계산 |
| `test_api_rules.py` | 임계치 검증(VAL-05), 태깅(VAL-06), 공통 에러 형식, CSV 수식 주입 방지 |
| `test_batch_execution.py` | advisory lock, stale 정리, worker watcher, 상태 fencing·경합·freshness |
| `test_daily_batch_safety.py` | bounded fallback, 후처리·normalizer 격리, LLM transaction 경계, fail-fast, cooldown, SLA |
| `test_monthly_batch_safety.py` | SBIZ·PERMIT fail-closed, content-addressed archive, 모집단 감소율 guard |
| `factories.py` | 테스트용 값 생성기(가상 상호명, 개인정보 없음) |

경고 1건은 `starlette/testclient.py`의 `anyio.abc.BlockingPortal` DeprecationWarning으로, 서드파티 내부 코드에서 발생하며 우리 코드와 무관하다.

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

> 기존 문서(1~9번)의 Bedrock 관련 서술은 설계 시점의 결정(목표 아키텍처)으로 보존한다. 2026-10-14부터 `4-project-principle.md` v1.6.0·`5-arch-diagram.md` v1.4.0은 "목표: Bedrock / 현재 MVP: LiteLLM Gateway"를 병기한다.

---

## 17. 미확정 사항

| # | 항목 | 상태 | 조치 |
|---|---|---|---|
| 1 | ~~지방행정 인허가 변동분 API 신청 (N-1)~~ | ✅ **해소(2026-09-30 승인, 2026-10-08 연동)** — 행안부 업종별 인허가 조회서비스 9종(S-10~S-18) | §10.1, `api/11-api-spec.md` |
| 2 | S-1 좌표계·사업자번호 제공 여부 | 미확인 | 테스트 호출로 확인 |
| 3 | ECOS / 오피넷 별도 포털 가입 | 미완료 | ecos.bok.or.kr, opinet.co.kr |
| 4 | ~~LiteLLM Gateway 인증키 형식~~ | ✅ **해소(2026-09-30)** — Virtual Key(`sk-...`)를 `Authorization: Bearer`로 전송. 실제 호출 성공 | — |
| 5 | ~~LLM 모델 확정~~ | ✅ **해소(2026-09-30)** — `claude-opus-5` | 제공 모델 목록은 §8.1 |
| 6 | ~~UC-07 "브리프 1건 5초" 미달성~~ | ✅ **해소(2026-09-30)** — EC2 실측 median 3.77초로 충족(§8.5). 개발 PC 수치(7.4초)로 인한 오판이었다 | 07:30 전체 SLA는 TOP20 × 지점 수로 별도 측정 필요 |
| 7 | 07:30 배치 전체 SLA | 계측 구현·P95 미측정 | 예약 실행별 결과는 `stage_stats.sla`에 저장됨. 파일럿 지점 수 확정 후 전체 실행 P95 측정 |

### 17.1 해소된 인프라 사항 (2026-09-29)

| 항목 | 결과 | 비고 |
|---|---|---|
| Tomcat ↔ serve 8080 포트 충돌 | ✅ 해소 | Tomcat disable, serve가 8080 사용 |
| Nginx myapp ↔ c-maker 설정 충돌 | ✅ 해소 | myapp.bak 백업, c-maker 적용 |
| PostgreSQL DB/계정 결정 | ✅ 확정 | 기존 `myapp_db`/`myapp_user` 사용, 신규 생성 없음. 테이블은 전용 스키마 `cmaker`(§4) |
| Node.js 버전 (v24 vs v20) | ✅ 확인 | nvm v24 현행 사용, 빌드 호환 문제 없음 |
| Python 3.14 패키지 호환성 | ✅ 해소 | **PyJWT 채택 완료**(`PyJWT==2.15.1`, python-jose 제거 — 3.13+ 빌드 이슈·CVE-2024-33663/33664). pydantic은 3.14용 wheel이 있는 2.13.5로 고정(§5.2) |

---

## 18. 프로젝트명 변경 사항

| 변경 전 | 변경 후 |
|---|---|
| BranchSense / branchsense | **C-MAKER** / **c-maker** |

기존 설계 문서(`1-domain-definition.md` ~ `9-style-guide.md`)의 "BranchSense" 표기는 C-MAKER로 일괄 변경 완료. 본 구현 가이드는 C-MAKER 명칭으로 작성되었다.

**사용자 화면 서비스 표시명은 NH Campaigner**다(2026-10-13~14, `frontend/index.html` `<title>`, 공식 시그니처 `frontend/public/brand/nh-campaigner.svg`, CRM 등록 파일 `내용` 접두어). 시스템·코드명(저장소, 배포 경로 `c-maker`, DB 스키마 `cmaker`, 파일명 `cmaker_*`)은 C-MAKER를 유지한다. 표시명의 기획 최종 확정은 `2-prd.md` 10장 이슈 1번에서 확인한다.

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
│   ├── config/pipeline.toml          # 배치 구조적 설정
│   ├── database/
│   │   ├── schema.sql                # DDL (cmaker 스키마)
│   │   ├── seed.sql                  # 초기 데이터 (BRANCH, USER, THRESHOLD_CONFIG, SIGNAL_WEIGHT)
│   │   └── patches/                  # 기존 DB용 패치 (2026-10-13_forecast_signals.sql)
│   ├── scripts/                      # 개발용 픽스처 (APP_ENV=dev)
│   ├── tests/                        # pytest
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/                          # React 19 + TypeScript
│   ├── dist/                         # 빌드 산출물 (serve가 서빙)
│   ├── package.json
│   └── vite.config.ts
├── deploy/
│   ├── c-maker.nginx.conf
│   ├── c-maker.cron
│   ├── c-maker-api.service
│   └── c-maker-frontend.service
└── docs/                             # 설계 문서
```
