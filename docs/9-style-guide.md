# C-MAKER 프론트엔드 스타일 가이드

- **버전**: v1.4.0
- **작성일**: 2026-08-26 (최종 수정: 2026-09-29)

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.0.0 | 2026-08-26 | 초안 작성 |
| v1.1.0 | 2026-09-08 | NH뱅크 인터넷뱅킹 UI 참고 캡처를 반영해 브랜드 컬러를 그린 계열로 조정, 버튼/배지/토글을 pill(완전 라운드) 형태로 변경, 상단 유틸리티 바·탭 내비게이션·토글 스위치 컴포넌트 추가 |
| v1.1.1 | 2026-09-08 | 문서 정합성 점검 결과 반영: 하위 문서 인용 버전 정정, 접근성 문구를 `2-prd.md` v1.1.0과 동일하게 "표시 개인화 옵션은 있으나 정식 a11y 기준은 미정의"로 조정 |
| v1.1.2 | 2026-09-08 | 큰글 모드(표시 개인화) 기능 제외 결정에 따라 §5.8 토글 스위치 컴포넌트를 삭제하고 이후 절 번호를 재정렬(5.9→5.8, 5.10→5.9, 5.11→5.10). 토글 관련 서술을 디자인 톤·토큰 절에서 제거 |
| v1.2.0 | 2026-09-08 | 배치 지연/실패 대비 수동 재연동 버튼(REQ-17, UC-18) 반영: §5.10 배너 컴포넌트에 우측 액션 슬롯(`.banner__action`, outline pill 버튼)과 진행중/쿨다운 상태 서술 추가 |
| v1.3.0 | 2026-09-08 | `report/db-schema-decisions-review.md` 검토 결과 반영: `8-wireframe.md`의 지점 등록/수정 화면(옛 §3) 제거에 따라 `8-wireframe.md` 장 번호 인용을 전부 갱신(4→3, 6→5, 7→6, 8→7). 지오코딩 검색 아이콘(🔍) 사용 예시를 제거(해당 화면이 사라져 근거 없음). 필수 항목 검증 서술의 예시 화면을 지점 등록 폼에서 임계치 관리 화면으로 교체 |
| v1.4.0 | 2026-09-29 | UI 시각 개선(토큰 값 변경·추가 없음): §5.1 태깅 버튼 선택/저장중 상태, §5.4 추천 카드 순위 칩·사업체명 굵기, §5.6 사이드바 아이콘·축소 모드 구현 규칙, §5.11 명부 현황 스트립·순위 칩, §5.12 브리프 상세 2단 배치, §5.13 공통 기반 스타일(포커스·줄바꿈·모션) 추가 |

---

## 0. 문서 목적 및 전제

본 문서는 프론트엔드(`4-project-principle.md` 6장, `7-execution-plan.md`의 FE 작업 항목) 개발 시 사용할 시각 스타일(컬러/타이포그래피/스페이싱/컴포넌트 톤)을 정의한다. `8-wireframe.md`(v1.3.0)에 정의된 실제 화면 구조에 스타일을 입힌다.

- 은행 영업점 실무자가 매일 아침 판단을 내리는 업무 도구라는 점을 최우선으로 반영한다 — 화려함보다 **신뢰감과 즉시 판독 가능성**을 우선한다.
- `2-prd.md`(v1.4.0) 6장에 따라 데스크톱 우선(1280px)·태블릿 대응(768px)으로 설계하며, 접근성(a11y) 세부 기준은 별도로 정의하지 않는다.
- `4-project-principle.md`(v1.5.0) 기준 프론트엔드 스택은 React 19 + TypeScript이며, 특정 CSS 프레임워크는 아직 채택하지 않았다. 아래 토큰은 CSS 커스텀 프로퍼티(`:root` 변수)로 정의해 CSS Modules 등 어떤 구현 방식에서도 재사용할 수 있게 했다.
- 은행 내부망 배포를 고려해 외부 CDN 웹폰트에 의존하지 않고 시스템 폰트 스택을 사용한다.
- 라이트/다크 두 테마의 토큰을 함께 정의한다. `<html data-theme="dark">` 속성 전환으로 다크모드를 구현한다.
- (v1.1.0) 2026-09-08 제공된 NH뱅크 인터넷뱅킹 화면 캡처를 시각 참고 자료로 반영한다. 브랜드 로고·문구·실제 계좌 정보를 그대로 재현하는 것이 목적이 아니라, **은행 실무자에게 이미 익숙한 톤(그린 브랜드 컬러, pill형 액션 버튼, 카드형 계좌 리스트, 상단 유틸리티 바 구성)** 을 BranchSense(C-MAKER)에도 일관되게 적용하기 위함이다.

---

## 1. 디자인 톤

- **화이트 베이스 + NH 그린 포인트**: 배경은 중립(화이트/라이트 그레이)을 기본으로 하고, 신뢰·행동 유도가 필요한 지점(주요 버튼, 활성 탭, 링크)에 NH 그린 한 가지로 브랜드·강조를 통일한다. 채도 높은 색은 상태 전달(성공/경고/위험)에만 절제해 사용한다.
- **데이터 밀도 우선**: 카드·표 위주의 정보 배치를 사용하고, 여백보다 스캔 가능성을 우선한다(태그 리스트업, 표, KPI 타일).
- **상태는 형태로도 표현**: 색상만이 아니라 배지·아이콘·굵기로 상태를 이중 인코딩한다(색약 사용자 및 저채도 화면 대응).
- **행동(action) 요소는 pill, 정보(container) 요소는 완만한 라운드**: 참고 화면의 주요 버튼(기본정보/거래내역/이체하기)·상태 태그(마이너스 대출)는 완전 라운드(`--radius-full`)로 "눌러서 실행하는 것"임을 형태로 드러낸다. 반면 카드·표·모달 등 콘텐츠를 담는 컨테이너는 기존대로 절제된 사각 라운드(`--radius-sm`/`--radius-md`)를 유지해 화면이 전부 둥글둥글해지는 것을 피한다.

---

## 2. 컬러

### 2.1 라이트 테마 (기본값)

```css
:root {
  /* Brand / Accent — NH뱅크 참고 캡처(2026-09-08)의 그린 톤에 맞춘 값. 정확한 브랜드 헥스코드는 §8 미확정 사항 참고 */
  --color-primary: #00a651;
  --color-primary-hover: #00913f;
  --color-primary-bg: #e2f5ea;

  /* Neutral */
  --color-bg: #f5f6f6;
  --color-surface: #ffffff;
  --color-surface-alt: #f0f2f2;      /* 사이드바, 테이블 헤더 배경 */
  --color-border: #dfe3e3;
  --color-text: #16191a;
  --color-text-secondary: #6b7576;   /* 메타 정보: 기준일, 출처 태그 */
  --color-text-disabled: #a3aaab;

  /* Semantic — success는 primary(그린)와 육안 혼동을 피하기 위해 청록 쪽으로 색상을 분리했다 */
  --color-success: #0e7c72;
  --color-success-bg: #dcf0ed;
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
  --color-primary: #3ecb7e;
  --color-primary-hover: #63d597;
  --color-primary-bg: #0f2c1c;

  --color-bg: #101414;
  --color-surface: #171c1c;
  --color-surface-alt: #1e2424;
  --color-border: #2b3232;
  --color-text: #e6eaea;
  --color-text-secondary: #b6bfbf;
  --color-text-disabled: #71797a;

  --color-success: #4fc9bd;
  --color-success-bg: #123330;
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

  --radius-sm: 4px;    /* 배지(사각형 변형), 입력창 */
  --radius-md: 8px;    /* 카드, 테이블, 모달 */
  --radius-lg: 12px;   /* KPI 타일 */
  --radius-full: 999px; /* pill: 주요 액션 버튼, 상태 태그 */

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

참고 캡처의 `기본정보`/`거래내역`/`이체하기` 버튼(꽉 찬 그린 pill)을 기준으로, 카드 내부의 즉시 실행 액션은 pill 형태를 사용한다.

| 종류 | 스타일 | 사용처 |
|---|---|---|
| Primary (pill) | `background: var(--color-primary)`, 흰 텍스트, `border-radius: var(--radius-full)`, `padding: var(--space-2) var(--space-4)`, medium | 저장, 로그인, 승인, 카드 내 인라인 액션(예: 방문 체크리스트 열기) |
| Primary (사각) | `background: var(--color-primary)`, 흰 텍스트, `border-radius: var(--radius-sm)`, medium | 폼 제출형 버튼(임계치 저장 등 페이지 전체 폭 버튼) — 카드 내부가 아닌 위치에서는 사각 라운드 유지 |
| Secondary (outline pill) | 배경 없음, `border: 1px solid var(--color-border)`, `border-radius: var(--radius-full)` | `관리` 드롭다운형 버튼처럼 pill 그룹과 나란히 놓이는 보조 액션 |
| Secondary (outline 사각) | 배경 없음, `border: 1px solid var(--color-border)`, `border-radius: var(--radius-sm)` | 취소, 필터 초기화 |
| Tag-Visited | `background: var(--color-success-bg)`, `color: var(--color-success)`, `border-radius: var(--radius-full)` | 태깅 '방문함' 버튼 (`8-wireframe.md` 3장) |
| Tag-Hold | `background: var(--color-warning-bg)`, `color: var(--color-warning)`, `border-radius: var(--radius-full)` | 태깅 '보류' 버튼 |
| Tag-Rejected | `background: var(--color-danger-bg)`, `color: var(--color-danger)`, `border-radius: var(--radius-full)` | 태깅 '부적합' 버튼 |
| Danger | `color: var(--color-danger)`, 배경 없음 | 캠페인 반려 |

Hover/active 시 `--color-primary-hover`로 전환, 비활성 상태는 `--color-text-disabled` + 클릭 불가.

- (v1.4.0) **태깅 버튼 선택 상태**: 현재 태깅된 버튼은 상태색(`--color-success`/`--color-warning`/`--color-danger`)으로 채우고 흰 글자 + 앞에 `✓`를 붙인다(색과 형태 이중 인코딩, §1). 흰 글자 대비는 세 색 모두 4.5:1 이상이다.
- (v1.4.0) **태깅 저장 중**: 저장 요청이 도는 짧은 동안의 비활성은 회색 전환 대신 `opacity: 0.55` + `cursor: progress`로 표현한다(목록 20건의 버튼이 동시에 회색으로 깜빡이는 것을 막기 위함). 권한·조건으로 인한 영구 비활성은 기존 규칙(`--color-text-disabled`)을 따른다.

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

- 오류 메시지는 입력창 바로 아래, `--font-size-xs` + `--color-danger`로 표시한다(`8-wireframe.md` 6장 임계치 관리 화면의 필수 항목 검증).
- 임계치 관리 화면(`8-wireframe.md` 6장)의 숫자 입력은 `text-align: right; font-variant-numeric: tabular-nums`를 적용한다.

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
.badge--outline {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
}
```

색상은 2.3절 매핑을 따른다(예: `.badge--visited { color: var(--color-success); background: var(--color-success-bg); }`). 표본부족·병합·절사 배지는 `.badge--dashed`를 사용한다. 참고 캡처의 `마이너스 대출` 태그처럼 계좌·사업체 속성을 부가 설명하는 중립 라벨(예: TOP 20 카드의 업종 라벨)에는 `.badge--outline`(흰 배경 + 회색 테두리 pill)을 사용한다 — 상태를 나타내는 배지(방문함/보류/부적합 등)와 형태를 구분해 혼동을 막는다.

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

- `8-wireframe.md` 3장 오늘의 접촉 TOP 20은 세로 리스트(카드 20개)로 배치하며, 태블릿 이하에서도 동일하게 1열 리스트를 유지한다(데이터 밀도 우선, 2장 참조).
- 태깅 완료된 카드는 `opacity: 0.75`로 낮추되 목록에서 사라지지 않는다(재태깅 가능성 유지). (v1.4.0) 마우스를 올리거나 카드 안에 포커스가 있으면 불투명도 1로 복원한다.
- (v1.4.0) 카드는 `순위 칩 | 본문(업종 배지·사업체명·사유) | 점수` 3열 그리드이며, 태깅 버튼은 본문 열 아래 줄에 둔다. 순위는 §5.11 순위 칩으로 표시한다.
- (v1.4.0) 사업체명은 `--font-size-md` + **bold**를 쓴다. Windows 기본 한글 폰트(맑은 고딕)에는 500 굵기가 없어 medium이 regular로 렌더링되기 때문이다. 같은 이유로 굵기 대비가 필요한 라벨(표의 항목명, 폼 라벨)도 bold를 쓴다.

### 5.5 KPI 스탯 타일

`8-wireframe.md` 5장(운영 브리핑), 7장(채택률 대시보드)에서 사용한다.

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
- (v1.4.0) 메뉴 항목은 20px 인라인 SVG 아이콘(`stroke: currentColor`) + 라벨로 구성한다(아이콘 라이브러리 미도입, §7). 1279px 이하에서는 사이드바 폭 64px 아이콘 전용 모드로 줄이고, 라벨은 화면에서만 숨겨 스크린리더에는 남긴다(`title`로 툴팁 제공).
- (v1.4.0) 지점 헤더는 `8-wireframe.md` 1장 목업처럼 사이드바 오른쪽 콘텐츠 열 상단에 둔다. 콘텐츠 영역 최대 폭은 1120px(넓은 모니터에서 카드 한 줄이 과도하게 길어지는 것 방지).

### 5.7 탭 내비게이션 (밑줄 인디케이터)

참고 캡처의 `출금계좌 · 저축성 · 대출 · 펀드 · 다른금융` 탭 전환 구조에 대응한다. `8-wireframe.md` 3장(추천 명부의 상태 필터 탭 등 동일 화면 내 뷰 전환)에서 사용한다.

```css
.tabs {
  display: flex;
  gap: var(--space-5);
  border-bottom: 1px solid var(--color-border);
}
.tab {
  padding: var(--space-2) 0 var(--space-3);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  border-bottom: 2px solid transparent;
}
.tab.is-active {
  color: var(--color-text);
  border-bottom-color: var(--color-primary);
}
```

- 사이드바(메뉴 계층 이동)와 탭(같은 계층 내 뷰 전환)의 역할을 혼용하지 않는다 — 탭은 사이드바 메뉴 하위의 2차 분류에만 사용한다.

### 5.8 상단 유틸리티 바

참고 캡처 최상단(`개인/기업/카드` 탭, `백승우 님 · 09:47 연장 · 로그아웃`, `외환·주택도시기금·보안센터·고객센터`)에 대응하는 공통 레이어. `8-wireframe.md` 1장 공통 레이아웃의 최상단 바에 적용한다.

- 배경 `--color-surface`, 하단 `border-bottom: 1px solid var(--color-border)`.
- 좌측: 로고 + 역할 전환 탭(있는 경우). 우측: 사용자명·세션 연장 타이머·로그아웃 — `--font-size-sm` + `--color-text-secondary`, 세션 연장 텍스트는 남은 시간이 5분 이하로 줄면 `--color-warning`로 전환한다.
- 최우측 보조 링크 그룹(고객센터 등 상시 노출 안내)은 `--font-size-xs` + `--color-text-secondary`로 본문보다 한 단계 낮은 위계를 준다.

### 5.9 데이터 테이블

`8-wireframe.md` 6장(임계치 관리), 7장(채택률 대시보드)에서 사용한다.

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

### 5.10 배너 (데이터 지연 · 미태깅 상기)

`8-wireframe.md` 1장(지연 배너), 3장(미태깅 배너)에서 사용한다.

```css
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--font-size-sm);
}
.banner__action {
  flex-shrink: 0;
}
```

- 배너 우측에 액션 버튼(예: `8-wireframe.md` 1장의 "수동 재연동", `ManualBatchTrigger`)을 둘 때는 `.banner__action` 슬롯에 §5.1의 **Secondary (outline pill)** 버튼을 사용한다 — 배너 자체의 경고색과 겹치지 않도록 배경 없는 outline 스타일을 쓰고, 배너 텍스트와 동일한 `--color-warning`을 테두리·글자색으로 사용한다.
- 액션 버튼이 요청 처리 중(예: 배치 재실행 진행 중)일 때는 버튼 라벨을 "재연동 중…"으로 바꾸고 `--color-text-disabled` + 클릭 불가 상태로 전환한다(§5.1 비활성 규칙과 동일).
- 쿨다운으로 버튼이 비활성인 경우, 버튼 자체보다 배너 우측의 보조 텍스트(`--font-size-xs` + `--color-text-secondary`)로 "N분 후 다시 시도 가능"을 표시해 배지·버튼과 시각적으로 구분한다.

### 5.11 명부 현황 스트립 · 순위 칩 (v1.4.0)

`8-wireframe.md` 3장의 "20건 중 N건 미태깅"을 오늘의 접촉 화면 제목 아래에 시각화한다. 순위 1~20이 칸 하나씩이며, 같은 칸 모양이 각 추천 카드의 순위 표시에도 쓰여 스트립의 n번 칸과 n위 카드가 한눈에 연결된다.

| 상태 | 칸 스타일 |
|---|---|
| UNTAGGED(미태깅) | `--color-surface` 배경 + `1px dashed var(--color-text-disabled)` + `--color-text-secondary` 숫자 (§5.3 `.badge--dashed`와 같은 "미완료" 형태) |
| VISITED / HOLD / REJECTED | 각각 `--color-success` / `--color-warning` / `--color-danger` 채움 + 흰 숫자 |

- 칸은 정보 요소이므로 pill이 아닌 `--radius-sm` 사각이다(§1). 스트립 28px, 카드 순위 칩 32px, 숫자는 bold + `tabular-nums`.
- 스트립은 보기 전용이다(클릭 동작 없음). 스크린리더에는 상태별 건수를 담은 한 문장으로 읽힌다.
- 오늘 명부의 처리 현황일 뿐 개인 성과 지표가 아니다(CLAUDE.md §0.7). 비율·달성률·순위 비교로 표기하지 않는다.
- 탐색 슬롯 여부는 칸에 구분하지 않는다(RULE-TARGET-04).
- 상태 필터 탭(§5.7)에는 상태별 건수를 `--font-size-xs` 보조 숫자로 붙인다(활성 탭의 숫자는 `--color-primary`).

### 5.12 브리프 상세 배치 (v1.4.0)

- 데스크톱(1280px 이상)은 `읽을 것(선정 사유·전화 화법) | 할 일(방문 체크리스트·접촉 결과 태깅)` 2단(우측 320px, 스크롤 시 고정)으로 두어 태깅 버튼이 항상 보이게 한다. 1279px 이하는 1단.
- 사실 문장의 출처 태그는 문장 바로 아래 줄에 둔다(문장 길이와 무관하게 같은 자리에서 확인). 본문 한 줄은 45em 이내.
- 전화 화법은 소리 내어 읽는 문장이므로 `--color-surface-alt` 배경 + 좌측 3px `--color-primary` 선의 인용 블록으로 구분한다.
- 체크리스트 체크박스는 `accent-color: var(--color-primary)`, 18px. 체크한 항목은 `--color-text-secondary` + 취소선(화면 내 표시만, 저장하지 않음).

### 5.13 공통 기반 스타일 (v1.4.0)

- 한글 줄바꿈은 어절 단위(`word-break: keep-all`)로 한다.
- 키보드 포커스는 모든 상호작용 요소에 `2px solid var(--color-primary)` 외곽선(`:focus-visible`)으로 표시한다.
- 모션은 사용자 행동에 대한 응답에만 짧게 쓴다(드롭다운 120ms, 확인 다이얼로그·저장 토스트 180ms). `prefers-reduced-motion: reduce`면 모두 끈다.
- 페이지 제목은 공통 `.page-title`(`--font-size-lg` bold), 설명은 `.page-description`, 불러오는 중·오류는 `.state-message`, 빈 목록은 점선 테두리의 `.state-panel`을 쓴다.

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

- 사용 위치: 사이드바 메뉴 아이콘, 상태 배지 접두 아이콘(경고 △, 지연 ⏱ 등 최소 텍스트 기호).
- 아이콘 크기: 인라인 `16px`, 사이드바 메뉴 `20px`.
- 별도 아이콘 폰트/라이브러리 도입 여부는 SETUP-03(`7-execution-plan.md`) 진행 시 결정하며, 이 문서는 크기·색상 토큰만 규정한다.

---

## 8. 참고 문서

- `1-domain-definition.md` (v1.4.0): 상태 값 정의(태깅값, 이벤트 상태, 캠페인 상태) — 색상 매핑 근거
- `2-prd.md` (v1.4.0): 6장 플랫폼/UI(반응형 웹, 접근성 기준 미정의)
- `4-project-principle.md` (v1.5.0): 6장 프론트엔드 디렉토리 구조
- `7-execution-plan.md` (v1.0.1): SETUP-03(프로젝트 초기 셋업, 디자인 토큰 반영 작업)
- `8-wireframe.md` (v1.3.0): 화면별 레이아웃 구조 (본 스타일 가이드가 스타일을 입히는 대상)
- `report/db-schema-decisions-review.md`: `8-wireframe.md` 장 번호 변경(지점 등록 화면 제외) 근거
- NH뱅크 인터넷뱅킹 화면 캡처 (사용자 제공, 2026-09-08): §1 디자인 톤, §2.1 브랜드 컬러, §5.1/5.3/5.7/5.8 컴포넌트(pill 버튼, outline 배지, 탭 밑줄, 상단 유틸리티 바)의 시각 참고 자료. 문서로 보관되어 있지 않으므로 실제 색상값 재확인이 필요할 경우 §9-미확정 사항 참고

---

## 9. 미확정 사항 — 구현 전 확인 필요

- **§2 색상 값의 정확도**: 본 절의 NH 그린 헥스코드(`#00a651` 등)는 참고 캡처를 육안으로 근사한 값이며, 실제 브랜드 가이드라인 문서와 대조되지 않았다. 최종 구현 전 정확한 브랜드 컬러 값을 디자인팀/브랜드 가이드에서 확인한다.
- **NH뱅크 UI와의 유사도 범위**: 이번 개정은 "실무자에게 익숙한 톤"을 참고하기 위함이며, C-MAKER는 NH뱅크 인터넷뱅킹의 로고·워드마크·레이아웃을 그대로 복제하지 않는다. 실제 화면 구현 시 상표·UI 유사도가 과도하지 않은지 사용자에게 재확인한다.
