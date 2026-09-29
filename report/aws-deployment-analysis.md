# BranchSense AWS 배포 인프라 분석 보고서

- **작성일**: 2026-09-29
- **대상 프로젝트**: BranchSense (영업점 신호 감지 + 접촉 명부 추천 시스템)
- **분석 범위**: agents/*.md 에이전트 정의, docs/* 프로젝트 문서, frontend/ 소스 구성

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
| **Frontend** | React 19 + TypeScript + Zustand + TanStack Query | Vite 빌드, SPA |
| **Backend (API)** | Python 3.12 + FastAPI | Uvicorn ASGI 서버 |
| **Backend (Batch)** | Python 3.12 | 일간/월간/주간 배치 파이프라인 |
| **DB 접근** | psycopg (직접 SQL, ORM 미사용) | |
| **DB** | PostgreSQL 17 | |
| **LLM** | AWS Bedrock AI Agent + Knowledge Base | 브리프·캠페인 문구 생성 |
| **공공 데이터** | data.go.kr 등 8종 API | 국세청, 행안부, 기상청 등 |

### 1.2 주요 데이터 소스 (공공 API)

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

| 에이전트 | 모델 | BranchSense 배포와의 관련도 | 역할 요약 |
|----------|------|--------------------------|----------|
| **backend-developer** | sonnet | ⭐⭐⭐ 높음 | FastAPI API·배치 구현, Docker·배포 파이프라인 |
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
- 환경별 설정 분리 (dev/staging/production)
- 시크릿 관리, 기능 플래그
- Prometheus 메트릭, OpenTelemetry 분산 추적
- 로그 구조화 (correlation ID 포함)

**frontend-developer** 에이전트에서 정의하는 빌드/배포 사항:
- TypeScript strict mode, 번들 최적화
- 빌드 파이프라인 및 배포 프로세스
- Storybook 문서화, 성능 메트릭

**api-designer** 에이전트에서 정의하는 API 표준:
- OpenAPI 3.1 명세, JWT 인증
- Rate limiting, CORS 설정
- API 버저닝 전략

---

## 3. AWS 인프라 구성도

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
│  │  │  │  PostgreSQL 17                                 │  │                           │   │ │
│  │  │  │  - Multi-AZ (선택)                              │◄─┘                           │   │ │
│  │  │  │  - 자동 백업 (7일 보존)                          │                              │   │ │
│  │  │  │  - Port: 5432                                  │                              │   │ │
│  │  │  └────────────────────────────────────────────────┘                              │   │ │
│  │  │                                                                                  │   │ │
│  │  └──────────────────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                                       │ │
│  └───────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  ┌─ AWS Bedrock ─────────────────────────┐    ┌─ 외부 공공 API ──────────────────────┐   │
│  │  AI Agent (브리프·캠페인 문구 생성)       │    │  data.go.kr (인허가, 국세청 등)      │   │
│  │  Knowledge Base (공개 상품설명서 RAG)     │    │  ECOS, 오피넷, 기상청 등             │   │
│  │                                        │    │                                     │   │
│  │  ※ VPC PrivateLink 경유 (보안팀 확인)    │    │  ※ EC2 Backend → HTTPS 아웃바운드    │   │
│  └────────────────────────────────────────┘    └─────────────────────────────────────┘   │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

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
| 아웃바운드 | 443 | 0.0.0.0/0 | 공공 API + Bedrock 호출 |
| 아웃바운드 | 5432 | RDS SG | DB 접속 |

**RDS Security Group**

| 방향 | 포트 | 소스/대상 | 용도 |
|------|------|----------|------|
| 인바운드 | 5432 | Backend EC2 SG | API·배치에서 DB 접근 |
| 인바운드 | 5432 | WorkSpaces SG | 운영자 psql 직접 접근 (REQ-01) |

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
┌─ RDS: PostgreSQL 17 ────────┐
│  RECOMMENDATION, BRIEF,      │
│  BUSINESS, EVENT 등 조회      │
└──────────────────────────────┘
```

### 4.2 배치 파이프라인 흐름 (매일 07:30 SLA)

```
┌─ EC2: Backend ─────────────────────────────────────────────────────────────┐
│                                                                             │
│  cron (00:00~07:00 실행) 또는 수동 재연동 (REQ-17)                           │
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
│       │     (탐색 슬롯 3건 포함)             │                                  │
│       │                                   │                                  │
│       ├─ ⑤ briefing ───────────────────┐  │                                  │
│       │     AWS Bedrock AI Agent 호출    │──→ Bedrock (HTTPS / PrivateLink)  │
│       │     + citation guard 검증        │                                   │
│       │                                  │                                   │
│       └─ ⑥ DB 적재                       │                                   │
│             SIGNAL, EVENT, RECOMMENDATION,│                                   │
│             BRIEF, CRM 파일 사전 생성      │──→ RDS PostgreSQL (5432)          │
│                                           │                                   │
│  07:30 이전 완료 (P95 SLA)                 │                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 모집단 적재 흐름 (월 1회)

```
run_monthly.py
    │
    ├─ ① 지방행정 인허가 전수 데이터 수집 (data.go.kr)
    │
    ├─ ② 좌표 변환 (EPSG:5174 → WGS84)
    │
    ├─ ③ BUSINESS 테이블 UPSERT (permit_mgt_no 기준 병합)
    │
    └─ ④ 적재 기준월 기록
         → RDS PostgreSQL
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
# 2. Node.js 20 설정
# 3. npm ci
# 4. npm run build (Vite 빌드)
# 5. SCP로 빌드 산출물을 Frontend EC2에 전송
# 6. SSH로 Nginx 재시작

# ── Backend 배포 Job ─────────────────
# 1. Checkout
# 2. Python 3.12 설정
# 3. pip install -r requirements.txt
# 4. pytest (테스트 실행)
# 5. SCP로 소스를 Backend EC2에 전송
# 6. SSH로 서비스 재시작 (systemd reload)
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
                          │     │   └─ ruff / mypy (backend)                           │
                          │     │                                                      │
                          │     ├─ Test                                                │
                          │     │   ├─ pytest (backend)                                │
                          │     │   └─ vitest (frontend, 추후)                          │
                          │     │                                                      │
                          │     ├─ Build                                               │
                          │     │   ├─ npm run build (frontend → dist/)                │
                          │     │   └─ pip freeze > requirements.txt (backend)         │
                          │     │                                                      │
                          │     └─ Deploy                                              │
                          │         ├─ Frontend EC2: SCP dist/ → SSH nginx reload      │
                          │         └─ Backend EC2: SCP src/ → SSH systemd restart     │
                          │                                                            │
                          └────────────────────────────────────────────────────────────┘
```

### 5.4 배포 시 필요한 GitHub 설정

| 항목 | 설정 위치 | 내용 |
|------|----------|------|
| **SSH Key** | GitHub → Settings → Secrets | EC2 접속용 private key |
| **EC2 Host** | GitHub → Settings → Secrets | Frontend/Backend EC2 Public IP 또는 도메인 |
| **AWS Credentials** | GitHub → Settings → Secrets | (Bedrock·RDS 접근 시 필요) |
| **Environment Vars** | GitHub → Settings → Variables | `VITE_API_BASE_URL` 등 빌드 환경변수 |
| **Branch Protection** | GitHub → Settings → Branches | main 브랜치 직접 push 방지, PR 필수 |

### 5.5 EC2 서버 사전 준비

**Frontend EC2**

```bash
# Nginx 설치 및 설정
sudo apt update && sudo apt install -y nginx

# /etc/nginx/sites-available/frontend
server {
    listen 80;
    server_name your-frontend-domain.com;

    root /var/www/frontend/dist;
    index index.html;

    # SPA 라우팅 지원
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 요청은 Backend EC2로 프록시
    location /api/ {
        proxy_pass http://BACKEND_EC2_PRIVATE_IP:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Backend EC2**

```bash
# Python 3.12 + 의존성
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip

# 가상환경 생성
python3.12 -m venv /opt/branchsense/venv
source /opt/branchsense/venv/bin/activate
pip install -r requirements.txt

# systemd 서비스 등록
# /etc/systemd/system/branchsense-api.service
[Unit]
Description=BranchSense API Server
After=network.target

[Service]
User=branchsense
WorkingDirectory=/opt/branchsense/backend
ExecStart=/opt/branchsense/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/opt/branchsense/.env

[Install]
WantedBy=multi-user.target

# 배치 cron 등록
# crontab -e
0 0 * * * /opt/branchsense/venv/bin/python /opt/branchsense/backend/run_daily.py
0 2 1 * * /opt/branchsense/venv/bin/python /opt/branchsense/backend/run_monthly.py
0 3 * * 1 /opt/branchsense/venv/bin/python /opt/branchsense/backend/run_weekly.py
```

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
| **장애 대응** | ❌ 공공 API 장애가 사용자 화면에 직접 영향. 대체 수단 없음 | ✅ 만료 캐시 반환(stale data) + 재시도 로직. 폴백 전략 구현 가능 |
| **로깅·모니터링** | ❌ 브라우저에서의 호출은 서버 로그에 남지 않음 | ✅ 호출 횟수, 응답시간, 에러율 등 서버 로그에 기록. 모니터링 대시보드 구성 가능 |
| **캐싱 효율** | △ 브라우저 메모리 캐시(TanStack Query)만 가능. 사용자별 독립 캐시 | ✅ 2중 캐시 구조 (브라우저 + 서버). 서버 캐시는 모든 사용자가 공유 |
| **개발 복잡도** | ✅ 단순. 프론트엔드에 API 클라이언트만 추가 | △ 백엔드 Router → Service → Client 3개 레이어 추가 필요 |
| **서버 비용** | ✅ 추가 서버 비용 없음 (이미 있는 Frontend EC2만 사용) | △ Backend EC2에 추가 부하 발생. 이미 배치용으로 존재하므로 한계적 추가 비용 |
| **Bedrock 연계** | ❌ 프론트에서 수집한 공공 데이터를 Bedrock과 결합하려면 결국 백엔드로 전달해야 함 | ✅ 서버에서 공공 데이터 + DB 데이터 + Bedrock 결과를 자유롭게 조합 |
| **감사 추적** | ❌ REQ-15(감사 추적 로그) 요건 충족 불가 | ✅ 모든 데이터 흐름이 서버를 경유하므로 완전한 감사 추적 가능 |

### 6.4 BranchSense 프로젝트에 대한 결론

**Case B (Backend 경유)를 권장합니다.** 이유:

1. **보안 요건**: 금융권 시스템으로 API Key 노출은 허용 불가 (PRD 7장 컴플라이언스)
2. **감사 추적**: REQ-15에서 모든 데이터 흐름의 감사 추적을 요구
3. **기존 아키텍처와 일관성**: PRD 5장 아키텍처에서 이미 배치 파이프라인이 공공 API를 서버에서 수집하는 구조
4. **호출 한도**: 국세청 API (1일 100만건), 인허가 데이터 등 한도 관리가 중요
5. **SLA 충족**: 07:30 SLA를 위한 폴백 전략은 서버 캐시가 필수
6. **Bedrock 연계**: 브리프 생성 시 공공 데이터와 LLM 결과를 서버에서 결합

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

| # | 작업 | 상세 | 우선순위 |
|---|------|------|----------|
| 1 | **VPC 생성** | CIDR: 10.0.0.0/16, Public/Private Subnet × 2 AZ | 필수 |
| 2 | **EC2 Frontend 인스턴스** | Amazon Linux 2023 또는 Ubuntu 22.04, Nginx 설치 | 필수 |
| 3 | **EC2 Backend 인스턴스** | Python 3.12, Nginx, 충분한 메모리(배치용) | 필수 |
| 4 | **RDS PostgreSQL 17** | Private Subnet, Multi-AZ (운영), 자동 백업 | 필수 |
| 5 | **Security Group 설정** | §3.3 참조, 최소 권한 원칙 | 필수 |
| 6 | **IAM Role 설정** | EC2 → Bedrock 접근용 IAM Role | 필수 |
| 7 | **AWS Bedrock 설정** | AI Agent + Knowledge Base 구성, 모델 접근 권한 | 필수 |
| 8 | **SSL 인증서** | ACM 또는 Let's Encrypt, HTTPS 적용 | 필수 |
| 9 | **도메인 설정** | Route 53 또는 기존 DNS에 A/CNAME 레코드 | 권장 |
| 10 | **CloudWatch 설정** | EC2/RDS 모니터링, 알람 구성 | 권장 |

### 7.2 애플리케이션 준비 작업

| # | 작업 | 상세 | 우선순위 |
|---|------|------|----------|
| 1 | **환경변수 파일 구성** | Backend: `.env` (DB_HOST, PUBLIC_API_KEY, AWS_REGION 등) | 필수 |
| 2 | **Frontend 빌드 환경변수** | `VITE_API_BASE_URL` (Backend EC2 주소) | 필수 |
| 3 | **DB 스키마 마이그레이션** | `database/schema.sql` 실행, 초기 데이터 적재 | 필수 |
| 4 | **BRANCH/USER 초기 데이터** | 운영자가 psql로 직접 INSERT (REQ-01) | 필수 |
| 5 | **공공 API 키 발급** | data.go.kr 서비스 키 신청 (8종 각각) | 필수 |
| 6 | **Bedrock AI Agent 구성** | Action Group 등록, Knowledge Base 색인 | 필수 |
| 7 | **Nginx 설정 파일** | Frontend: SPA 라우팅 + API 프록시, Backend: 리버스 프록시 | 필수 |
| 8 | **systemd 서비스 등록** | FastAPI 자동 시작·재시작 | 필수 |
| 9 | **cron 등록** | 일간(run_daily.py), 월간(run_monthly.py), 주간(run_weekly.py) | 필수 |
| 10 | **로그 수집 설정** | CloudWatch Agent 또는 파일 로그 로테이션 | 권장 |

### 7.3 GitHub CI/CD 구성 작업

| # | 작업 | 상세 | 우선순위 |
|---|------|------|----------|
| 1 | **GitHub Repository 생성** | 모노레포 (frontend/ + backend/) 또는 분리 | 필수 |
| 2 | **GitHub Secrets 등록** | SSH Key, EC2 Host, 환경변수 | 필수 |
| 3 | **GitHub Actions 워크플로우** | Lint → Test → Build → Deploy 파이프라인 | 필수 |
| 4 | **Branch Protection Rules** | main 브랜치 보호, PR 리뷰 필수 | 권장 |
| 5 | **.gitignore 정비** | `.env`, `node_modules/`, `__pycache__/`, `dist/` | 필수 |
| 6 | **PR 템플릿** | 변경사항 체크리스트, 테스트 결과 기록 | 권장 |

### 7.4 보안 검토 필요 사항 (PRD 6장·10장 연계)

| # | 사항 | 상태 | 담당 |
|---|------|------|------|
| 1 | AWS Bedrock 리전 선택 | 보안팀 확인 필요 | 보안·IT |
| 2 | VPC PrivateLink 사용 여부 | 보안팀 확인 필요 | 보안·IT |
| 3 | 데이터 반출 경로 승인 | 보안팀 확인 필요 | 보안 |
| 4 | USER 비밀번호 평문 저장 → 해싱 전환 검토 | 검토 필요 | 개발·보안 |
| 5 | 공공 API 키 관리 방안 | AWS Secrets Manager 권장 | 개발 |

---

## 8. 비용 추정 및 권장 사양

### 8.1 인스턴스 권장 사양

| 리소스 | 사양 | 월 추정비용 (서울 리전) | 비고 |
|--------|------|----------------------|------|
| **EC2 Frontend** | t3.small (2 vCPU, 2 GB) | ~$19 | 정적 파일 서빙, 부하 낮음 |
| **EC2 Backend** | t3.medium (2 vCPU, 4 GB) | ~$38 | API + 배치 프로세스 동시 운영 |
| **RDS PostgreSQL** | db.t3.medium (2 vCPU, 4 GB) | ~$70 | 20 GB gp3 스토리지 포함 |
| **AWS Bedrock** | 사용량 기반 | ~$50~200 | 모델·호출량에 따라 변동 |
| **EBS (Frontend)** | 20 GB gp3 | ~$2 | |
| **EBS (Backend)** | 50 GB gp3 | ~$5 | 배치 스냅샷 임시 저장 |
| **데이터 전송** | — | ~$10 | 월 100 GB 기준 |
| **합계** | — | **~$194~344/월** | |

> MVP 파일럿 단계에서는 위 사양으로 충분합니다. 전행 확산(Phase 3) 시에는 Backend EC2를 t3.large 이상으로 업그레이드하고, RDS Multi-AZ를 활성화하는 것을 권장합니다.

### 8.2 확장 시 고려사항

| 단계 | 추가 고려 | 이유 |
|------|----------|------|
| Phase 2 | Backend EC2 → t3.large (8 GB) | 운영 예측(REQ-10), 상품 안내(REQ-11) 배치 추가 |
| Phase 2 | Redis (ElastiCache) 추가 | 공공 API 캐싱 전용, 서버 메모리 절약 |
| Phase 3 | ALB + Auto Scaling Group | 전행 확산 시 동시 접속자 증가 대비 |
| Phase 3 | RDS Multi-AZ 활성화 | 99.5% 가용성 SLA 충족 |
| Phase 3 | CloudFront CDN | Frontend 정적 파일 글로벌 캐싱 |

---

## 부록 A. 전체 아키텍처 한눈에 보기

```
┌──────────────┐         ┌───────────────┐        ┌─────────────────────────────────────┐
│  WorkSpaces  │── git ──│    GitHub      │── CI ──│          AWS Cloud (서울 리전)         │
│  (개발 환경)   │  push   │  (소스 관리)    │  /CD   │                                     │
└──────────────┘         └───────────────┘        │  ┌─────────┐     ┌──────────────┐   │
                                                   │  │Frontend │────▶│  Backend      │   │
                              ┌─────────────┐      │  │ EC2     │ API │  EC2          │   │
                              │ 사용자       │      │  │ (Nginx  │     │  (FastAPI     │   │
                              │ (브라우저)    │─────▶│  │  +React)│     │   +Batch)     │   │
                              └─────────────┘      │  └─────────┘     └──┬─────┬──────┘   │
                                                   │                     │     │           │
                                                   │              ┌──────┘     └──────┐   │
                                                   │              ▼                    ▼   │
                                                   │  ┌─────────────────┐  ┌─────────────┐│
                                                   │  │ RDS PostgreSQL  │  │ Bedrock     ││
                                                   │  │ (Private Subnet)│  │ (AI Agent   ││
                                                   │  └─────────────────┘  │ + KB)       ││
                                                   │                       └─────────────┘│
                                                   │                  ▲                    │
                                                   │                  │ HTTPS              │
                                                   │          ┌───────┴────────┐           │
                                                   │          │  공공 API       │           │
                                                   │          │  (data.go.kr   │           │
                                                   │          │   등 8종)       │           │
                                                   │          └────────────────┘           │
                                                   └───────────────────────────────────────┘
```

---

## 부록 B. 배포 체크리스트

배포 전 최종 확인 사항:

- [ ] VPC, Subnet, Internet Gateway 생성 완료
- [ ] EC2 인스턴스 2대 (Frontend, Backend) 실행 중
- [ ] RDS PostgreSQL 17 인스턴스 실행 중
- [ ] Security Group 규칙 적용 완료
- [ ] SSL 인증서 발급 및 Nginx HTTPS 설정
- [ ] GitHub Actions Secrets 등록 (SSH Key, EC2 Host)
- [ ] Frontend: `npm run build` 성공, Nginx 설정 완료
- [ ] Backend: `requirements.txt` 설치, systemd 서비스 등록
- [ ] Backend: `.env` 파일 배치 (DB 접속정보, API Key, AWS 설정)
- [ ] DB: `schema.sql` 실행, BRANCH/USER 초기 데이터 INSERT
- [ ] Cron: 일간/월간/주간 배치 등록
- [ ] Bedrock: AI Agent + Knowledge Base 구성 완료
- [ ] IAM Role: EC2 → Bedrock 접근 권한 확인
- [ ] 공공 API 키: 8종 서비스 키 발급 및 `.env`에 등록
- [ ] CI/CD: GitHub Actions 워크플로우 테스트 배포 성공
- [ ] 모니터링: CloudWatch 알람 구성 (CPU, 메모리, 디스크)
- [ ] 07:30 SLA 테스트: run_daily.py 수동 실행 → 완료 시간 확인

---

*본 보고서는 BranchSense 프로젝트의 agents/*.md 에이전트 정의, docs/* 아키텍처 문서, frontend/ 소스 구성을 기반으로 작성되었습니다.*
