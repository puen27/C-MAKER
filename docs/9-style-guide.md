# BranchSense 프론트엔드 스타일 가이드

- **버전**: v1.0.0
- **작성일**: 2026-08-26

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.0.0 | 2026-08-26 | 초안 작성 |

---

## 0. 문서 목적 및 전제

본 문서는 프론트엔드(`4-project-principle.md` 6장, `7-execution-plan.md`의 FE 작업 항목) 개발 시 사용할 시각 스타일(컬러/타이포그래피/스페이싱/컴포넌트 톤)을 정의한다. `8-wireframe.md`(v1.0.0)에 정의된 실제 화면 구조에 스타일을 입힌다.

- 은행 영업점 실무자가 매일 아침 판단을 내리는 업무 도구라는 점을 최우선으로 반영한다 — 화려함보다 **신뢰감과 즉시 판독 가능성**을 우선한다.
- `2-prd.md`(v1.0.0) 6장에 따라 데스크톱 우선(1280px)·태블릿 대응(768px)으로 설계하며, 접근성(a11y) 세부 기준은 별도로 정의하지 않는다.
- `4-project-principle.md`(v1.0.0) 기준 프론트엔드 스택은 React 19 + TypeScript이며, 특정 CSS 프레임워크는 아직 채택하지 않았다. 아래 토큰은 CSS 커스텀 프로퍼티(`:root` 변수)로 정의해 CSS Modules 등 어떤 구현 방식에서도 재사용할 수 있게 했다.
- 은행 내부망 배포를 고려해 외부 CDN 웹폰트에 의존하지 않고 시스템 폰트 스택을 사용한다.
- 라이트/다크 두 테마의 토큰을 함께 정의한다. `<html data-theme="dark">` 속성 전환으로 다크모드를 구현한다.

---

## 1. 디자인 톤

- **화이트/차콜 베이스 + 딥 틸(deep teal) 포인트**: 배경은 중립을 기본으로 하고, 신뢰를 상징하는 딥 틸 하나로 브랜드·강조를 통일한다. 채도 높은 색은 상태 전달(성공/경고/위험)에만 절제해 사용한다.
- **데이터 밀도 우선**: 카드·표 위주의 정보 배치를 사용하고, 여백보다 스캔 가능성을 우선한다(태그 리스트업, 표, KPI 타일).
- **상태는 형태로도 표현**: 색상만이 아니라 배지·아이콘·굵기로 상태를 이중 인코딩한다(색약 사용자 및 저채도 화면 대응).
- **완만한 라운드**: 놀이적인 pill 형태 대신 업무 도구에 어울리는 절제된 사각 라운드(`--radius-sm`/`--radius-md`)를 사용한다.

---

## 2. 컬러

### 2.1 라이트 테마 (기본값)

```css
:root {
  /* Brand / Accent */
  --color-primary: #0e5c63;
  --color-primary-hover: #0a464c;
  --color-primary-bg: #dceaea;

  /* Neutral */
  --color-bg: #f3f6f6;
  --color-surface: #ffffff;
  --color-surface-alt: #e9eeee;      /* 사이드바, 테이블 헤더 배경 */
  --color-border: #d8e0e0;
  --color-text: #0f1718;
  --color-text-secondary: #5f7072;   /* 메타 정보: 기준일, 출처 태그 */
  --color-text-disabled: #9aaaaa;

  /* Semantic */
  --color-success: #2c6e49;
  --color-success-bg: #e3f1e8;
  --color-warning: #b3610a;
  --color-warning-bg: #f6e9d8;
  --color-danger: #9b2c2c;
  --color-danger-bg: #f5e1e1;
  --color-info: #2a5c8a;
  --color-info-bg: #e5eef5;
}
```

### 2.2 다크 테마 (`[data-theme="dark"]`)

```css
[data-theme="dark"] {
  --color-primary: #5fb6bc;
  --color-primary-hover: #7fc9ce;
  --color-primary-bg: #14312f;

  --color-bg: #0c1213;
  --color-surface: #131b1c;
  --color-surface-alt: #1a2425;
  --color-border: #263334;
  --color-text: #e2eaea;
  --color-text-secondary: #b7c4c4;
  --color-text-disabled: #6c7a7a;

  --color-success: #74c295;
  --color-success-bg: #163523;
  --color-warning: #dfa055;
  --color-warning-bg: #2e2418;
  --color-danger: #e08c85;
  --color-danger-bg: #331d1d;
  --color-info: #7db3e0;
  --color-info-bg: #172433;
}
```

### 2.3 상태 색상 매핑

`1-domain-definition.md`에 정의된 값 목록에 각각 다음 색을 배정한다(5.3절 배지 컴포넌트에 적용).

| 값 | 색상 토큰 | 비고 |
|---|---|---|
| 태깅 = VISITED(방문함) | `--color-success` / `--color-success-bg` | 채택률 분자에 반영되는 긍정 신호 |
| 태깅 = HOLD(보류) | `--color-warning` / `--color-warning-bg` | 판단 유보, 분모에는 포함 |
| 태깅 = REJECTED(부적합) | `--color-danger` / `--color-danger-bg` | 이후 배제 필터에 반영됨을 시각적으로 경고 |
| EVENT.status = ACTIVE | `--color-info` / `--color-info-bg` | 오늘 반영된 활성 이벤트 |
| EVENT.status = MERGED / TRIMMED | `--color-text-disabled`, 배경 없음 | 참고용, 강조하지 않음 |
| 데이터 지연 배지 (RULE-SENSE-04) | `--color-warning` / `--color-warning-bg` | 기준일 지연 안내 |
| 표본부족 배지 (RULE-LEARN-03) | `--color-text-secondary`, 배경 없음, 점선 테두리 | 가중치 미갱신 상태 |
| CAMPAIGN.status = DRAFT | `--color-text-secondary` 배경 없음 | |
| CAMPAIGN.status = MANAGER_REVIEW | `--color-info` / `--color-info-bg` | |
| CAMPAIGN.status = APPROVED / HANDED_OFF | `--color-success` / `--color-success-bg` | |

---

## 3. 타이포그래피

시스템 기본 한글 산세리프 폰트 스택을 사용한다(외부 웹폰트 로드 없음, 내부망 배포 신뢰성 우선).

```css
:root {
  --font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
    "Malgun Gothic", "맑은 고딕", sans-serif;
  --font-family-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;

  --font-size-xs: 12px;   /* 메타 정보, 배지, 출처 태그 */
  --font-size-sm: 14px;   /* 보조 텍스트, 표 본문 */
  --font-size-md: 16px;   /* 기본 본문, 입력창 */
  --font-size-lg: 20px;   /* 섹션 타이틀 (예: "오늘의 접촉") */
  --font-size-xl: 28px;   /* KPI 타일 강조 수치 */

  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-bold: 700;

  --line-height-tight: 1.3;
  --line-height-normal: 1.6;
}
```

- KPI 타일의 강조 수치(`--font-size-xl`, bold)는 숫자 정렬을 위해 `font-variant-numeric: tabular-nums`를 함께 지정한다.
- 추천 카드의 사업체명은 `--font-size-md` + medium, 점수·순위는 `--font-size-sm` + `--color-text-secondary`.
- 출처 태그(`[소스명·기준일]`)는 `--font-size-xs` + `--color-text-secondary` + `--font-family-mono`로 데이터 성격을 시각적으로 구분한다.

---

## 4. 스페이싱 · 라운드 · 그림자

4px 기준 배수 스케일을 사용한다.

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;

  --radius-sm: 4px;    /* 배지, 입력창 */
  --radius-md: 8px;    /* 카드, 테이블, 모달 */
  --radius-lg: 12px;   /* KPI 타일 */

  --shadow-card: 0 1px 2px rgba(15, 23, 24, 0.05), 0 4px 12px -8px rgba(15, 23, 24, 0.15);
  --shadow-modal: 0 4px 16px rgba(15, 23, 24, 0.2);
}
```

- 콘텐츠 영역 좌우 여백: 데스크톱 `--space-6`, 태블릿 `--space-4`.
- 추천 카드 내부 패딩: `--space-4`.
- KPI 타일 내부 패딩: `--space-5`.

---

## 5. 컴포넌트 스타일

`8-wireframe.md`의 각 화면 요소에 대응하는 컴포넌트 스타일이다.

### 5.1 버튼

| 종류 | 스타일 | 사용처 |
|---|---|---|
| Primary | `background: var(--color-primary)`, 흰 텍스트, `border-radius: var(--radius-sm)`, medium | 저장, 로그인, 승인 |
| Secondary (outline) | 배경 없음, `border: 1px solid var(--color-border)` | 취소, 필터 초기화 |
| Tag-Visited | `background: var(--color-success-bg)`, `color: var(--color-success)` | 태깅 '방문함' 버튼 (`8-wireframe.md` 4장) |
| Tag-Hold | `background: var(--color-warning-bg)`, `color: var(--color-warning)` | 태깅 '보류' 버튼 |
| Tag-Rejected | `background: var(--color-danger-bg)`, `color: var(--color-danger)` | 태깅 '부적합' 버튼 |
| Danger | `color: var(--color-danger)`, 배경 없음 | 캠페인 반려 |

Hover/active 시 `--color-primary-hover`로 전환, 비활성 상태는 `--color-text-disabled` + 클릭 불가.

### 5.2 입력창

```css
.input {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-md);
  background: var(--color-surface);
  color: var(--color-text);
}
.input:focus {
  border-color: var(--color-primary);
  outline: 2px solid var(--color-primary-bg);
}
.input.error {
  border-color: var(--color-danger);
}
```

- 오류 메시지는 입력창 바로 아래, `--font-size-xs` + `--color-danger`로 표시한다(`8-wireframe.md` 3장 지점 등록 폼의 필수 항목 검증).
- 임계치 관리 화면(`8-wireframe.md` 7장)의 숫자 입력은 `text-align: right; font-variant-numeric: tabular-nums`를 적용한다.

### 5.3 상태 배지

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}
.badge--dashed {
  background: transparent;
  border: 1px dashed var(--color-border);
  color: var(--color-text-secondary);
}
```

색상은 2.3절 매핑을 따른다(예: `.badge--visited { color: var(--color-success); background: var(--color-success-bg); }`). 표본부족·병합·절사 배지는 `.badge--dashed`를 사용한다.

### 5.4 카드 / 추천 리스트 항목

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  padding: var(--space-4);
}
```

- `8-wireframe.md` 4장 오늘의 접촉 TOP 20은 세로 리스트(카드 20개)로 배치하며, 태블릿 이하에서도 동일하게 1열 리스트를 유지한다(데이터 밀도 우선, 2장 참조).
- 태깅 완료된 카드는 `opacity: 0.75`로 낮추되 목록에서 사라지지 않는다(재태깅 가능성 유지).

### 5.5 KPI 스탯 타일

`8-wireframe.md` 6장(운영 브리핑), 8장(채택률 대시보드)에서 사용한다.

```css
.stat-tile {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}
.stat-tile__value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  font-variant-numeric: tabular-nums;
}
.stat-tile__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
```

- 증가 추세는 `--color-success`, 감소는 `--color-danger` 삼각 화살표(▲▼)로 값 옆에 함께 표기한다.

### 5.6 사이드바 내비게이션

`8-wireframe.md` 1장 공통 레이아웃에 대응한다.

- 배경 `--color-surface-alt`, 우측 `border-right: 1px solid var(--color-border)`.
- 비활성 메뉴: `color: var(--color-text-secondary)`, regular.
- 활성 메뉴: `color: var(--color-primary)`, medium, 좌측 3px `border-left: var(--color-primary)`, 배경 `--color-primary-bg`.
- 역할별로 노출되지 않는 메뉴(`8-wireframe.md` 1장 표)는 DOM에서 아예 렌더링하지 않는다(숨김 처리가 아님).

### 5.7 데이터 테이블

`8-wireframe.md` 7장(임계치 관리), 8장(채택률 대시보드)에서 사용한다.

```css
.table th {
  background: var(--color-surface-alt);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  color: var(--color-text-secondary);
  text-align: left;
  padding: var(--space-2) var(--space-3);
}
.table td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-sm);
}
.table td.numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
```

### 5.8 배너 (데이터 지연 · 미태깅 상기)

`8-wireframe.md` 1장(지연 배너), 4장(미태깅 배너)에서 사용한다.

```css
.banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--font-size-sm);
}
```

---

## 6. 반응형 브레이크포인트

`2-prd.md` 6장(데스크톱 우선, 태블릿 대응)에 따라 기준값을 다음과 같이 확정한다.

```css
/* 태블릿: ~1279px (기본, 사이드바는 아이콘만 노출되는 축소 모드) */
/* 데스크톱: 1280px 이상 (사이드바 전체 라벨 노출) */
@media (min-width: 1280px) { /* 데스크톱 전체 레이아웃 */ }
```

- 1279px 이하에서는 사이드바가 아이콘 전용 축소 모드로 전환되고, KPI 타일 3열 그리드가 2열로 줄어든다.
- 모바일 전용 레이아웃은 정의하지 않는다(`8-wireframe.md` 0장 전제).

---

## 7. 아이콘

업무 도구의 성격상 장식적 아이콘 사용을 최소화한다.

- 사용 위치: 사이드바 메뉴 아이콘, 상태 배지 접두 아이콘(경고 △, 지연 ⏱ 등 최소 텍스트 기호), 지오코딩 검색 아이콘(🔍, `8-wireframe.md` 3장).
- 아이콘 크기: 인라인 `16px`, 사이드바 메뉴 `20px`.
- 별도 아이콘 폰트/라이브러리 도입 여부는 SETUP-03(`7-execution-plan.md`) 진행 시 결정하며, 이 문서는 크기·색상 토큰만 규정한다.

---

## 8. 참고 문서

- `1-domain-definition.md` (v1.0.0): 상태 값 정의(태깅값, 이벤트 상태, 캠페인 상태) — 색상 매핑 근거
- `2-prd.md` (v1.0.0): 6장 플랫폼/UI(반응형 웹, 접근성 미정의)
- `4-project-principle.md` (v1.0.0): 6장 프론트엔드 디렉토리 구조
- `7-execution-plan.md` (v1.0.0): SETUP-03(프로젝트 초기 셋업, 디자인 토큰 반영 작업)
- `8-wireframe.md` (v1.0.0): 화면별 레이아웃 구조 (본 스타일 가이드가 스타일을 입히는 대상)
