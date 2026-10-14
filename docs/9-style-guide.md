# C-MAKER 프론트엔드 스타일 가이드

- **버전**: v1.5.0
- **작성일**: 2026-08-26 (최종 수정: 2026-10-14)

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
| v1.5.0 | 2026-10-14 | 현재 구현(`frontend/src/styles/tokens.css`, 컴포넌트 CSS)과 일치하도록 정정: 주색을 NH 그린 `#00a651`에서 농협 CI Human Blue `#0066B3`로 바꾼 `NH-Campaigner-UI-proposal.html` '개발 전달용' CI 변수 구조(§2.1~2.2)로 갱신, 구현에 없는 다크 테마 절 삭제, 상태 색상 매핑을 `--status-*` 토큰으로 정정(§2.3). §5.1 기록 버튼(흰 바탕 + 선택 시 `--status-*` 채움, 라운드 사각) 정정. 삭제된 명부 현황 스트립·순위 칩(옛 §5.11)을 오늘 기록 패널·신호별 대상·한 줄 명부 행으로 교체하고, 브랜드 시그니처(§5.14)·출처 도장/데이터 기준 도장(§5.15)·기록 저장 토스트(§5.16) 절 추가. §5.4·§5.8·§5.10·§5.12 실제 스타일로 정정, §9 미확정 사항 갱신 |

---

## 0. 문서 목적 및 전제

본 문서는 프론트엔드(`4-project-principle.md` 6장, `7-execution-plan.md`의 FE 작업 항목) 개발 시 사용할 시각 스타일(컬러/타이포그래피/스페이싱/컴포넌트 톤)을 정의한다. `8-wireframe.md`(v1.4.0)에 정의된 실제 화면 구조에 스타일을 입힌다.

- 은행 영업점 실무자가 매일 아침 판단을 내리는 업무 도구라는 점을 최우선으로 반영한다 — 화려함보다 **신뢰감과 즉시 판독 가능성**을 우선한다.
- `2-prd.md`(v1.4.0) 6장에 따라 데스크톱 우선(1280px)·태블릿 대응(768px)으로 설계하며, 접근성(a11y) 세부 기준은 별도로 정의하지 않는다.
- `4-project-principle.md`(v1.5.0) 기준 프론트엔드 스택은 React 19 + TypeScript이며, 특정 CSS 프레임워크는 아직 채택하지 않았다. 아래 토큰은 CSS 커스텀 프로퍼티(`:root` 변수, `frontend/src/styles/tokens.css`)로 정의해 어떤 구현 방식에서도 재사용할 수 있게 했다. 컴포넌트 스타일은 컴포넌트별 일반 CSS 파일에 둔다.
- 은행 내부망 배포를 고려해 외부 CDN 웹폰트에 의존하지 않고 시스템 폰트 스택을 사용한다.
- (v1.5.0) 테마는 라이트 한 가지만 구현되어 있다. 옛 버전의 다크 테마(`[data-theme="dark"]`) 토큰은 `tokens.css`에 없어 삭제했다.
- (v1.1.0) 2026-09-08 제공된 NH뱅크 인터넷뱅킹 화면 캡처를 시각 참고 자료로 반영한다. 브랜드 로고·문구·실제 계좌 정보를 그대로 재현하는 것이 목적이 아니라, **은행 실무자에게 이미 익숙한 톤(pill형 액션 버튼, 카드형 리스트, 상단 유틸리티 바 구성)** 을 C-MAKER(화면 표시명 NH Campaigner)에도 일관되게 적용하기 위함이다.
- (v1.5.0) 이후 루트 `NH-Campaigner-UI-proposal.html`의 제안을 반영해 색상을 농협 CI 변수(주색 Human Blue)로 교체하고, 상단 바·로그인에 **NH Campaigner 공식 시그니처**(심볼+워드마크)를 쓴다. 화면 표시 서비스명은 'NH Campaigner'이며 C-MAKER는 시스템·코드명이다.

---

## 1. 디자인 톤

- **화이트 베이스 + Human Blue 포인트**: 배경은 중립(화이트/라이트 그레이 `--paper`)을 기본으로 하고, 신뢰·행동 유도가 필요한 지점(주요 버튼, 활성 탭·메뉴, 링크, 선택 상태)에 농협 CI Human Blue(`--primary`) 한 가지로 브랜드·강조를 통일한다. 채도 높은 색은 상태 전달(기록 상태, 경고/위험)에만 절제해 사용한다.
- **데이터 밀도 우선**: 표·한 줄 행 위주의 정보 배치를 사용하고, 여백보다 스캔 가능성을 우선한다(한 화면에 명부 6~7곳이 보이게 한다).
- **상태는 형태로도 표현**: 색상만이 아니라 배지·아이콘·굵기·`✓`·글자 라벨로 상태를 이중 인코딩한다(색약 사용자 및 저채도 화면 대응). 옐로우(`--status-hold`)는 흰 배경 대비가 낮으므로 늘 글자 라벨과 함께 쓴다.
- **행동(action) 요소와 정보(container) 요소의 형태 구분**: 화면 단위의 주요 액션(로그인, 수동 재연동)은 pill(`--radius-full`)로 "눌러서 실행하는 것"임을 드러낸다. 카드·표·패널·모달 등 콘텐츠 컨테이너는 절제된 사각 라운드(`--radius-sm`/`--radius-md`, 일부 패널 10px)를 유지한다. (v1.5.0) 명부 행 안에서 반복되는 기록 버튼과 CRM 등록 파일 버튼은 제안서에 따라 `--radius-md` 사각 라운드다(§5.1).

---

## 2. 컬러

### 2.1 농협 CI 변수와 기본 팔레트

`frontend/src/styles/tokens.css`의 실제 값이다. CI 3색은 `NH-Campaigner-UI-proposal.html`의 '개발 전달용' 화면 값이며, 사내 매뉴얼 값으로 최종 확인이 필요하다(§9).

```css
:root {
  /* 농협 CI — 화면용 값, 사내 매뉴얼 값으로 최종 확인 (NH-Campaigner-UI-proposal.html '개발 전달용') */
  --nh-human-blue:   #0066B3;  /* 주 색: 버튼, 링크, 선택 */
  --nh-nature-green: #1FB25A;  /* 브랜드 그린 */
  --nh-heart-yellow: #FFC20E;  /* 보류, 강조 */

  --primary:         var(--nh-human-blue);
  --primary-strong:  #00528F;  /* 버튼 hover */
  --primary-tint:    #EAF2FA;  /* 선택 배경 */
  --ink:             #1B2A38;  /* 본문 */
  --ink-2:           #47596B;  /* 보조 글자 */
  --ink-3:           #637284;  /* 흐린 글자 (흰 배경 4.9:1) */
  --line:            #DCE3EA;
  --paper:           #F3F5F7;  /* 앱 배경 */

  --status-visited:  #13803F;  /* 방문함, 흰 글자 5.0:1 */
  --status-hold:     var(--nh-heart-yellow);
  --status-hold-ink: #3B2C00;  /* 보류 버튼 글자 8.4:1 */
  --status-excluded: #5B6875;  /* 부적합, 흰 글자 5.7:1 */
}
```

- `--nh-nature-green`은 정의만 되어 있고 현재 컴포넌트 CSS에서 직접 쓰지 않는다.
- 이 파일의 값을 임의로 바꾸거나 새 색상 값을 추가하지 않는다(`tokens.css` 상단 주석). 변경이 필요하면 본 문서를 먼저 갱신한다.

### 2.2 기존 `--color-*` 토큰 (CI 변수를 가리키는 별칭)

v1.4.0까지의 `--color-*` 이름은 그대로 두고, 브랜드·중립 값은 §2.1 CI 변수를 가리키도록 바꿨다. 기존 컴포넌트는 `--color-*`를, 제안서 반영 컴포넌트(오늘 기록·신호별 대상·명부 행·출처 도장·브리프 상세 등)는 `--primary`/`--ink*`/`--line`/`--status-*`를 직접 쓴다.

```css
:root {
  /* Brand / Accent — 기존 토큰 이름은 유지하고 CI 변수를 가리킨다 */
  --color-primary: var(--primary);
  --color-primary-hover: var(--primary-strong);
  --color-primary-bg: var(--primary-tint);

  /* Neutral */
  --color-bg: var(--paper);
  --color-surface: #ffffff;
  --color-surface-alt: #f0f2f2;      /* 사이드바, 테이블 헤더 배경 */
  --color-border: var(--line);
  --color-text: var(--ink);
  --color-text-secondary: var(--ink-2);   /* 메타 정보: 기준일, 출처 */
  --color-text-muted: var(--ink-3);       /* (v1.5.0 추가) 흐린 글자 */
  --color-text-disabled: #a3aaab;

  /* Semantic — 값은 v1.4.0과 동일 */
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

- 시맨틱 색은 기록 상태에는 쓰지 않는다(기록 상태는 §2.3의 `--status-*`). 현재 용도: `--color-warning` 지연 배너·세션 만료 경고·로그인 만료 안내, `--color-info` 정보 배너(§5.10), `--color-danger` 입력 오류·저장 실패 토스트·재연동 실패 안내, `--color-success` 임계치 저장 완료 문구.

### 2.3 상태 색상 매핑

`1-domain-definition.md`에 정의된 값 목록에 각각 다음 색을 배정한다(§5.1 기록 버튼, §5.3 배지, §5.11 명부 행·오늘 기록 패널에 공통 적용).

| 값 | 색상 토큰 | 비고 |
|---|---|---|
| 태깅 = VISITED(방문함) | `--status-visited` 채움 + 흰 글자 | 채택률 분자에 반영되는 긍정 신호. 그린 |
| 태깅 = HOLD(보류) | `--status-hold` 채움 + `--status-hold-ink` 글자 | 판단 유보, 분모에는 포함. 옐로우(흰 글자 불가) |
| 태깅 = REJECTED(부적합) | `--status-excluded` 채움 + 흰 글자 | 이후 배제 필터에 반영됨. (v1.5.0) 빨강(`--color-danger`)에서 회색으로 변경 |
| 태깅 = UNTAGGED(기록 전) | 배지 `.badge--dashed`, 오늘 기록 패널은 `--paper` 바탕 + `--line` 테두리 | 미완료 형태 |
| EVENT.status = ACTIVE | `--color-info` / `--color-info-bg` | 오늘 반영된 활성 이벤트 |
| EVENT.status = MERGED / TRIMMED | `--color-text-disabled`, 배경 없음 | 참고용, 강조하지 않음 |
| 데이터 지연 (RULE-SENSE-04) | 대시보드 도장: `--status-hold` 테두리 + "지연" 라벨(`--status-hold` 바탕 / `--status-hold-ink` 글자). 그 외 화면 배너: `--color-warning` / `--color-warning-bg` | §5.15, §5.10 |
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

  --font-size-xs: 12px;   /* 메타 정보, 배지, 출처 도장 */
  --font-size-sm: 14px;   /* 보조 텍스트, 표 본문 */
  --font-size-md: 16px;   /* 기본 본문, 입력창 */
  --font-size-lg: 20px;   /* 섹션 타이틀 (예: "임계치 관리") */
  --font-size-xl: 28px;   /* 강조 수치, 브리프 상호명 */

  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-bold: 700;

  --line-height-tight: 1.3;
  --line-height-normal: 1.6;
}
```

- 강조 수치(오늘 기록 패널의 기록 수 등, `--font-size-xl` bold)는 숫자 정렬을 위해 `font-variant-numeric: tabular-nums`를 함께 지정한다.
- 명부 행의 상호명은 `--font-size-md` + 600, 순위 숫자는 19px + 600 + `--ink-3` + `tabular-nums`다. 점수는 표시하지 않는다.
- (v1.5.0) 출처는 `[소스명·기준일]` 글자 태그 대신 **출처 도장**(§5.15)으로 표시한다. 도장은 `--font-size-xs` + `--ink-2`이고 날짜만 600 + `--ink` + `tabular-nums`로 강조한다(고정폭 글꼴 미사용). `--font-family-mono`는 임계치 변경 이력의 "이전값 → 이후값"에만 쓴다.
- (v1.5.0) 제안서 반영 컴포넌트는 토큰 외 크기·굵기(13px, 12.5px, 14.5px, 15px, 19px, 30px, 600 등)를 직접 쓴다. 대시보드 헤드라인은 30px bold. 토큰화 여부는 §9 참고.

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

  --radius-sm: 4px;    /* 배지(사각형 변형), 입력창, 배너 */
  --radius-md: 8px;    /* 카드, 테이블, 모달, 기록 버튼, 드롭다운 */
  --radius-lg: 12px;   /* KPI 타일 */
  --radius-full: 999px; /* pill: 주요 액션 버튼, 상태 태그 */

  --shadow-card: 0 1px 2px rgba(15, 23, 24, 0.05), 0 4px 12px -8px rgba(15, 23, 24, 0.15);
  --shadow-modal: 0 4px 16px rgba(15, 23, 24, 0.2);
}
```

- 콘텐츠 영역 좌우 여백: 데스크톱 `--space-6`, 태블릿 `--space-4`.
- (v1.5.0) 대시보드의 패널·명부 시트, 브리프 카드는 `--line` 1px 테두리 + 10px 라운드이며 그림자를 쓰지 않는다. `--shadow-card`는 로그인 카드·임계치 표에, `--shadow-modal`은 드롭다운·확인 다이얼로그·토스트에 쓴다.
- KPI 타일 내부 패딩: `--space-5`.

---

## 5. 컴포넌트 스타일

`8-wireframe.md`의 각 화면 요소에 대응하는 컴포넌트 스타일이다.

### 5.1 버튼

참고 캡처의 꽉 찬 pill 버튼을 기준으로, 화면 단위의 주요 액션은 pill 형태를 사용한다.

| 종류 | 스타일 | 사용처 |
|---|---|---|
| Primary (pill) | `background: var(--color-primary)`, 흰 텍스트, `border-radius: var(--radius-full)`, `padding: var(--space-2) var(--space-5)`, medium | 로그인(44px 전체 폭), 승인 |
| Primary (사각) | `background: var(--color-primary)`, 흰 텍스트, `border-radius: var(--radius-sm)`, `padding: var(--space-2) var(--space-4)`, medium | 임계치 저장, 확인 다이얼로그의 확인(예: 수동 재연동 [실행]). (v1.5.0) CRM 등록 파일 받기 버튼은 이 변형에 `--radius-md` + 600 굵기 + 14px 다운로드 아이콘 + `▾`를 더한다 |
| Secondary (outline pill) | `--color-surface` 배경, `border: 1px solid var(--color-border)`, `border-radius: var(--radius-full)`. hover 시 테두리·글자 `--color-primary` | 수동 재연동(배너·안내 줄 안에서는 §5.10 규칙) |
| Secondary (outline 사각) | `--color-surface` 배경, `border: 1px solid var(--color-border)`, `border-radius: var(--radius-sm)` | 취소(확인 다이얼로그) |
| 기록 버튼 (방문함/보류/부적합) | 미선택: `--color-surface` 배경 + `--line` 테두리 + `--ink-2` 글자, 높이 32px, `--radius-md`, 13px. hover 시 테두리 `--ink-3`·글자 `--ink`. 선택: 아래 상태색 채움 | 명부 행(`8-wireframe.md` 3장)·브리프 상세(4장) |
| Danger | `color: var(--color-danger)`, 배경 없음 | 캠페인 반려 |

Primary hover는 `--color-primary-hover`(`--primary-strong`)로 전환한다. 일반 비활성 상태는 `--color-text-disabled` 글자 + `--color-surface-alt` 배경 + `--color-border` 테두리 + 클릭 불가.

- (v1.5.0 정정) **기록 버튼 선택 상태**: 현재 기록된 버튼은 §2.3의 `--status-*` 토큰으로 채운다 — 방문함 `--status-visited` + 흰 글자, 보류 `--status-hold` + `--status-hold-ink` 글자, 부적합 `--status-excluded` + 흰 글자. 굵기 600 + 앞에 `✓`를 붙인다(색과 형태 이중 인코딩, §1). 대비는 각각 5.0:1, 8.4:1, 5.7:1이다(`tokens.css` 주석 값). v1.4.0의 `--color-success`/`--color-warning`/`--color-danger` 채움과 pill 형태는 더 이상 쓰지 않는다.
- 부적합이 선택된 버튼은 "부적합 · {사유}"로 라벨을 바꾸고, 사유 드롭다운(§5.13 모션)에서 현재 사유는 `--status-excluded` + `✓`로 표시한다.
- **기록 저장 중**: 저장 요청이 도는 짧은 동안의 비활성은 회색 전환 대신 `opacity: 0.55` + `cursor: progress`로 표현하고, 선택된 버튼은 상태색을 유지한다(목록 20건의 버튼이 동시에 회색으로 깜빡이는 것을 막기 위함). 권한·조건으로 인한 영구 비활성은 일반 비활성 규칙을 따른다.

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
- 임계치 관리 화면(`8-wireframe.md` 6장)의 숫자 입력은 `text-align: right; font-variant-numeric: tabular-nums`를 적용한다(폭 104px, 높이 36px). 고정값 항목은 입력창 대신 `.badge--dashed` "발효 즉시 (고정)"를 보여준다.

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
/* 기록 상태 배지 — 기록 버튼과 같은 CI 상태색 */
.badge--visited  { color: #ffffff;                  background: var(--status-visited); }
.badge--hold     { color: var(--status-hold-ink);   background: var(--status-hold); }
.badge--rejected { color: #ffffff;                  background: var(--status-excluded); }
.badge--info     { color: var(--color-info);        background: var(--color-info-bg); }
```

- 기록 상태 배지는 기록 권한이 없는 지점장에게 명부 행·브리프 상세의 현재 기록 결과를 읽기 전용으로 보여줄 때 쓴다(기록 전 = `.badge--dashed`).
- 표본부족·병합·절사·고정값 배지는 `.badge--dashed`를 사용한다.
- 속성을 부가 설명하는 중립 라벨에는 `.badge--outline`(흰 배경 + 회색 테두리 pill)을 쓴다 — 현재는 지점 헤더의 역할 라벨이다. (v1.5.0) 명부의 업종은 배지가 아니라 상호명 아래 13px `--ink-3` 보조 글자로 바뀌었다(§5.11).

### 5.4 카드

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  padding: var(--space-4);
}
```

- 일반 콘텐츠 컨테이너(로그인 폼 등)의 기본형이다.
- (v1.5.0) 오늘의 접촉 TOP 20은 카드 20개 대신 **명부 시트 안의 한 줄 행**으로 바뀌었다(§5.11). v1.4.0의 "순위 칩 | 본문 | 점수 3열 그리드", 태깅 완료 카드 `opacity: 0.75`는 구현에서 삭제되었다.
- 사업체명 등 굵기 대비가 필요한 라벨은 bold(또는 600)를 쓴다. Windows 기본 한글 폰트(맑은 고딕)에는 500 굵기가 없어 medium이 regular로 렌더링되기 때문이다.

### 5.5 KPI 스탯 타일

`8-wireframe.md` 5장(운영 브리핑), 7장(채택률 대시보드)에서 사용한다(두 화면 모두 미구현, Phase 2).

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

- 폭 200px, 배경 `--color-surface-alt`, 우측 `border-right: 1px solid var(--color-border)`.
- 비활성 메뉴: `color: var(--color-text-secondary)`, regular, `--font-size-sm`. hover 시 `--color-text` + `--color-surface` 배경.
- 활성 메뉴: `color: var(--color-primary)`, medium, 좌측 3px `border-left: var(--color-primary)`, 배경 `--color-primary-bg`.
- 역할별로 노출되지 않는 메뉴와 미구현(Phase 2·3) 메뉴(`8-wireframe.md` 1장 표)는 DOM에서 아예 렌더링하지 않는다(숨김 처리가 아님).
- 메뉴 항목은 20px 인라인 SVG 아이콘(`stroke: currentColor`) + 라벨로 구성한다(아이콘 라이브러리 미도입, §7). 1279px 이하에서는 사이드바 폭 64px 아이콘 전용 모드로 줄이고, 라벨은 화면에서만 숨겨 스크린리더에는 남긴다(`title`로 툴팁 제공).
- 지점 헤더는 사이드바 오른쪽 콘텐츠 열 상단에 둔다(`--color-surface` 배경, 하단 `--color-border`). 콘텐츠 영역 최대 폭은 1120px(넓은 모니터에서 한 줄이 과도하게 길어지는 것 방지).

### 5.7 탭 내비게이션 (밑줄 인디케이터)

참고 캡처의 탭 전환 구조에 대응한다. `8-wireframe.md` 3장(명부의 기록 상태 탭 등 동일 화면 내 뷰 전환)에서 사용한다.

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
.tab__count {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-regular);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}
.tab.is-active .tab__count {
  color: var(--color-primary);
}
```

- 사이드바(메뉴 계층 이동)와 탭(같은 계층 내 뷰 전환)의 역할을 혼용하지 않는다 — 탭은 사이드바 메뉴 하위의 2차 분류에만 사용한다.
- 명부 시트 상단의 기록 상태 탭은 시트 헤더 줄에 들어가므로 `--font-size-sm`으로 줄이고 탭 자체의 하단선은 없앤다(시트 헤더의 `--line` 하단선을 공유).

### 5.8 상단 유틸리티 바

`8-wireframe.md` 1장 공통 레이아웃의 최상단 바(`TopUtilityBar`)에 적용한다.

- 최소 높이 64px, 배경 `--color-surface`, 상단 3px `--primary` 선, 하단 `1px solid var(--line)`. 좌우 패딩 `--space-5`(1279px 이하 `--space-4`).
- 좌측: 브랜드 시그니처(§5.14, 30px) + 1px × 22px `--line` 구분선 + 부제(13px `--ink-3`). 1279px 이하에서는 구분선·부제를 숨긴다.
- 우측: 13px `--ink-2`. 사용자명은 600 `--ink`. 세션 타이머는 `tabular-nums`이며 남은 시간이 5분 이하로 줄면 `--color-warning` + medium + `⏱`로 전환한다. "연장"·"로그아웃"은 배경 없는 텍스트 버튼(13px medium `--primary`, hover `--primary-strong` + 밑줄)이다.
- (v1.5.0) v1.1.0의 보조 링크 그룹(고객센터 등)은 구현되지 않아 삭제했다.

### 5.9 데이터 테이블

`8-wireframe.md` 6장(임계치 관리), 7장(채택률 대시보드)에서 사용한다.

```css
.table th {
  background: var(--color-surface-alt);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  text-transform: uppercase;
  color: var(--color-text-secondary);
  text-align: left;
  padding: var(--space-2) var(--space-4);
}
.table td {
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-sm);
  vertical-align: top;
}
.table td.numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
```

- 표 전체는 `--color-surface` + `--color-border` 테두리 + `--radius-md` + `--shadow-card`. 임계치 변경 이력은 해당 행 아래 펼침 행(`--color-surface-alt` 배경)으로 보여준다.

### 5.10 배너 (데이터 지연 · 정보 안내)

`8-wireframe.md` 1장(지연 배너), 3장(상권사유비율 초과·어제 미기록 안내)에서 사용한다.

```css
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
}
.banner--warning { background: var(--color-warning-bg); color: var(--color-warning); }
.banner--info    { background: var(--color-info-bg);    color: var(--color-info); }
.banner__action {
  flex-shrink: 0;
}
```

- 경고 톤(`.banner--warning`, `role="alert"`): 대시보드 외 화면의 데이터 지연 배너, 재연동 실패 안내.
- (v1.5.0) 정보 톤(`.banner--info`, `role="status"`): 상권사유비율 초과 안내, 명부가 비어 있을 때의 어제 미기록 안내, 재연동 완료 안내.
- 배너 우측에 액션 버튼(예: "수동 재연동", `ManualBatchTrigger`)을 둘 때는 `.banner__action` 슬롯에 §5.1의 **Secondary (outline pill)** 버튼을 높이 32px로 줄여 쓴다 — 배경 없이 테두리·글자를 배너 글자색(`currentColor`)과 같게 한다. hover 시 `--color-surface` 배경.
- 액션 버튼이 요청 처리 중일 때는 라벨을 "재연동 중…"으로 바꾸고 `--color-text-disabled` + `--color-border` 테두리 + 클릭 불가로 전환한다.
- 쿨다운·예상 완료 시각 등 보조 정보는 버튼 왼쪽 보조 텍스트(`.banner__hint`, `--font-size-xs` + `--color-text-secondary`)로 표시한다. 배너를 닫는 [닫기]는 밑줄 텍스트 버튼이다.
- 오늘의 접촉 화면은 배너 대신 데이터 기준 도장 아래 안내 줄(§5.15)을 쓴다.

### 5.11 오늘의 접촉 명부: 오늘 기록 · 신호별 대상 · 한 줄 명부 행 (v1.5.0)

v1.4.0의 명부 현황 스트립·순위 칩은 구현에서 삭제되고 아래 세 컴포넌트로 대체되었다(`NH-Campaigner-UI-proposal.html` 변경 포인트 4·5·7). 대시보드 상단 밴드는 `아침 브리핑 | 오늘 기록(260px) | 신호별 대상(272px)` 3열이며, 1279px 이하 2열(브리핑이 한 줄 전체), 767px 이하 1열이다.

**오늘 기록 패널** (`TodayRecordPanel`)

- 패널: `--color-surface` + `--line` 테두리 + 10px 라운드, 제목 15px bold.
- "기록한 수/ 전체 곳": 기록 수만 `--font-size-xl` bold `--ink`, 나머지 `--font-size-sm` `--ink-2`, `tabular-nums`.
- 비율 막대: 높이 10px, `--paper` 바탕 + `--line` 안쪽 테두리. 방문함·보류·부적합 구간을 `--status-visited`/`--status-hold`/`--status-excluded`로 채운다(기록 전은 빈 바탕). 스크린리더에는 "N곳 중 M곳 기록: 방문함 a, 보류 b, 부적합 c" 한 문장으로 읽힌다.
- 범례: 2열, 10px 사각 견본 + 라벨 + 건수(600 `--ink`, 오른쪽 정렬). 기록 전 견본은 `--paper` + `--line` 테두리.
- 어제 미기록 줄: 7px `--status-hold` 점 + "어제 기록하지 않은 곳 **N곳**". 하단 안내 "기록은 내일 명부에 반영됩니다."(12.5px `--ink-2`)는 `--line` 구분선 아래에 둔다.
- 오늘 명부의 처리 현황일 뿐 개인 성과 지표가 아니다(CLAUDE.md §0.7). **비율(%)·달성률·순위 비교로 표기하지 않는다.** 탐색 슬롯 여부는 구분하지 않는다(RULE-TARGET-04).

**신호별 대상 패널** (`SignalBarsPanel`)

- 패널 형태는 오늘 기록과 같다. 부제 12.5px `--ink-3`.
- 각 줄은 `신호명(84px, 말줄임) | 막대 | 건수(600 `--ink`)` 그리드의 버튼이다. 막대 트랙 8px `--paper`, 채움 `--primary`(최대 건수 대비 비율).
- hover와 선택(`aria-pressed="true"`) 상태는 `--primary-tint` 배경 + `--ink` 글자, 선택은 600 굵기를 더한다.
- 선택 시 명부 도구 영역에 "{신호명}만 보는 중" 칩이 나타난다: 높이 28px, 14px 라운드, `--primary-tint` 배경 + `--primary` 글자 12.5px 600, 우측 22px 원형 × 해제 버튼.

**한 줄 명부 행** (`RecommendationCard`)

- 명부 시트(`--color-surface` + `--line` 테두리 + 10px 라운드) 안에 행을 `--line` 1px 구분선으로 잇는다. 시트 헤더 줄에 기록 상태 탭(§5.7)과 도구(신호 칩·CRM 등록 파일 버튼)가 들어간다.
- 행은 `순위(28px) | 상호명·업종(200px) | 사유·출처 | 기록 버튼` 4열 그리드, hover 시 `#f8fafc` 배경 + 상호명 `--primary`.
- 순위 19px 600 `--ink-3` 오른쪽 정렬. 상호명 `--font-size-md` 600 `--ink`(링크, hover/포커스 시 `--primary` + 밑줄). 업종 13px `--ink-3`. 사유 14.5px 한 줄 말줄임(1279px 이하 줄바꿈 허용), 그 아래 출처 도장(§5.15).
- 기록 상태는 행 왼쪽 3px 안쪽 막대로 표시한다(`--status-visited`/`--status-hold`/`--status-excluded`, 기록 전은 없음). 부적합 행은 상호명·사유를 `--ink-3`로 흐린다. 점수·탐색 슬롯·어제 미기록 표시는 행에 두지 않는다.
- 1279px 이하는 `순위 | 나머지` 2열로 바꾸고 사유·버튼을 상호명 아래 줄로 내린다.

### 5.12 브리프 상세 배치

- 데스크톱(1280px 이상)은 `읽을 것(사업장·근거·날씨 참고·방문 전 확인) | 통화와 기록(전화 화법·접촉 결과)` 2단(우측 372px, `position: sticky`)으로 두어 기록 버튼이 항상 보이게 한다. 1279px 이하는 1단. 카드·패널은 `--line` 테두리 + 10px 라운드.
- 상호명은 `--font-size-xl` bold. 사업장 속성(업종·거리·주소)은 `--ink-3` 라벨 + 본문 값의 가로 나열.
- **핵심 근거**는 `--primary-tint` 배경 + 좌측 3px `--primary` 선 블록, 라벨("핵심 근거") `--font-size-xs` 600 `--primary`, 본문 15.5px·한 줄 45em 이내, 출처 도장은 문장 아래 줄. **보조 근거**는 `--line` 구분선 목록이며 출처 도장을 문장 오른쪽 열에 둔다(라벨 `--ink-3`).
- 추천상품·날씨 참고는 근거와 분리된 보조 블록(안내 문구 12.5~13px `--ink-3`)이다.
- 전화 화법은 단계 라벨(`인사/용건/약속`, 12.5px 600 `--ink-3`) + 문장(14.5px, 줄높이 1.65)의 번호 목록이며 단계 사이를 `--line`으로 나눈다. 제목 옆 생성 방식 배지는 높이 22px·11px 라운드 — "AI 작성"은 `--primary` 테두리·글자, "기본 화법"은 `--line` 테두리 + `--ink-3`. [화법 복사]는 `--line` 테두리의 34px 사각 보조 버튼.
- 통화 안내(고정 문구)는 `--line` 점선 테두리 + `--radius-md` 블록, 제목 옆 "고정 문구" 태그(pill, `--ink-3`)로 AI 화법과 구분한다.
- 체크리스트 체크박스는 16px, `accent-color: var(--primary)`. 체크한 항목은 `--ink-3` + 취소선(화면 내 표시만, 저장하지 않음). 데스크톱 2열, 1279px 이하 1열.

### 5.13 공통 기반 스타일

- 한글 줄바꿈은 어절 단위(`word-break: keep-all`)로 한다.
- 키보드 포커스는 모든 상호작용 요소에 `2px solid var(--color-primary)` 외곽선(`:focus-visible`)으로 표시한다.
- 모션은 사용자 행동에 대한 응답에만 짧게 쓴다(드롭다운 120ms, 확인 다이얼로그·기록 저장 토스트 180ms). `prefers-reduced-motion: reduce`면 모두 끈다.
- 페이지 제목은 공통 `.page-title`(`--font-size-lg` bold), 설명은 `.page-description`, 불러오는 중·오류는 `.state-message`, 빈 목록은 점선 테두리의 `.state-panel`을 쓴다(명부 시트 안에서는 테두리 없이 가운데 정렬 `--ink-3` 문구).
- (v1.5.0) 대시보드·브리프 하단 투명성 문구는 14px 정보 아이콘 + 12.5px `--ink-3` 한 줄이다.

### 5.14 브랜드 시그니처 (v1.5.0)

`BrandSignature` — 상단 유틸리티 바(§5.8)와 로그인 화면에 쓴다.

- NH Campaigner 공식 시그니처(심볼 + 'NH Campaigner' 워드마크가 하나로 묶인 원본 `public/brand/nh-campaigner.svg`)를 **변형 없이** 쓴다. 원본 비율(약 6.5:1)을 유지하도록 높이만 지정한다 — 기본 30px, 로그인 40px. 색·비율·요소 배치를 바꾸거나 일부만 잘라 쓰지 않는다.
- 워드마크가 시그니처에 들어 있으므로 옆에 서비스명을 글자로 다시 쓰지 않는다. 로그인 화면에서는 시그니처 이미지(alt "NH Campaigner")가 `h1` 역할을 한다.
- 파일을 불러오지 못하면 "NH Campaigner" 글자로 대체한다: bold `--ink`, 19px(로그인은 `--font-size-xl`), 줄바꿈 없음.

### 5.15 출처 도장 · 데이터 기준 도장 (v1.5.0)

**출처 도장** (`SourceStamp`) — 데이터 기준 도장, 명부 행, 브리프 근거에서 같은 모양으로 쓴다(RULE-BRIEF-01).

- 형태: "문서 아이콘 + 출처명 + **MM.DD**". 높이 22px, 좌우 패딩 7px, `--line` 1px 테두리, 3px 라운드(정보 요소이므로 pill 아님), `--color-surface` 배경, `--font-size-xs` `--ink-2`, 줄바꿈 없음.
- 아이콘은 12px 문서 모양 인라인 SVG, 선 색 `--primary`. 날짜는 600 `--ink` `tabular-nums`. 원본 태그 "소스명·YYYY-MM-DD"를 해석해 날짜를 `MM.DD`로 줄여 쓴다(형식이 맞지 않으면 출처명만).
- 툴팁(`title`)이 있는 도장은 `cursor: help`.

**데이터 기준 도장** (`DataFreshnessStamps`) — 대시보드 아침 브리핑 아래.

- "데이터 기준" 라벨(12.5px `--ink-3`) 뒤에 출처별 도장을 나열한다(줄바꿈 허용).
- 대체 데이터 사용(지연) 출처: 도장 테두리를 `--status-hold`로 바꾸고 날짜 뒤에 "지연" 라벨(`--status-hold` 바탕 + `--status-hold-ink` 글자, 11px bold, 2px 라운드)을 붙인다 — 옐로우는 늘 글자 라벨과 함께 쓴다(§1).
- 미수집 출처: 날짜 자리에 "미수집"을 `--ink-3` medium으로 쓴다.
- 안내 줄(배치 실패·미수집 등 도장만으로 알 수 없는 상황): 7px `--status-hold` 점 + 13px `--ink-2` 문구, 지점장에게는 같은 줄에 수동 재연동 버튼. 오류(재연동 실패)는 `--color-danger` 글자. [닫기]는 13px `--primary` 텍스트 버튼.

### 5.16 기록 저장 토스트 (v1.5.0)

`TagUndoToast` — 기록 직후 화면 하단 가운데에 고정으로 띄운다(UC-09 "저장 직후 되돌리기").

- 어두운 바탕(`--color-text` 배경 + `--color-surface` 글자), `--radius-md`, `--shadow-modal`, 패딩 `--space-3` `--space-4`, `--font-size-sm`, 하단 여백 `--space-5`, 화면 폭 - 48px 이내.
- 구성: "{상호명} · {상태} 저장됨" + [되돌리기](배경 없는 밑줄 텍스트 버튼, bold, `--color-primary-bg` 글자) + [×] 닫기. 포커스 외곽선은 `--color-primary-bg`.
- 저장 실패 시 배경을 `--color-danger`로 바꾸고 오류 문구만 보여준다.
- 아래에서 짧게 올라오며 나타나고(180ms) 10초 뒤 자동으로 닫힌다. 되돌리기 요청 중에는 [되돌리기]를 `opacity: 0.6` 비활성으로 둔다. `role="status"`로 스크린리더에 알린다.

---

## 6. 반응형 브레이크포인트

`2-prd.md` 6장(데스크톱 우선, 태블릿 대응)에 따라 기준값을 다음과 같이 확정한다.

```css
/* 태블릿: ~1279px (사이드바는 아이콘만 노출되는 축소 모드) */
/* 데스크톱: 1280px 이상 (사이드바 전체 라벨 노출) */
@media (max-width: 1279px) { /* 태블릿 축소 레이아웃 */ }
```

- 1279px 이하에서는 사이드바가 아이콘 전용 축소 모드로 전환되고, 상단 바 부제가 숨겨지며, 대시보드 상단 밴드가 2열·명부 행이 2열로, 브리프 상세가 1단으로 바뀐다. KPI 타일(미구현) 3열 그리드는 2열로 줄인다.
- (v1.5.0) 대시보드 상단 밴드와 시트 헤더 줄에는 767px 이하 1열·줄바꿈 규칙이 추가로 있다. 그 외 모바일 전용 레이아웃은 정의하지 않는다(`8-wireframe.md` 0장 전제).

---

## 7. 아이콘

업무 도구의 성격상 장식적 아이콘 사용을 최소화한다.

- 사용 위치: 사이드바 메뉴 아이콘, 출처 도장 문서 아이콘, CRM 등록 파일 다운로드 아이콘, 신호 칩 해제(×), 화법 복사, 뒤로 가기, 투명성 문구 정보 아이콘, 경고 기호(⚠, ⏱ 등 최소 텍스트 기호).
- 아이콘 크기: 사이드바 메뉴 `20px`, 인라인 `14px`(칩·버튼·투명성 문구), 출처 도장 `12px`. 선 색은 `currentColor`(출처 도장만 `--primary`).
- (v1.5.0) 별도 아이콘 폰트/라이브러리는 도입하지 않고 인라인 SVG를 쓴다.

---

## 8. 참고 문서

- `1-domain-definition.md` (v1.4.0): 상태 값 정의(태깅값, 이벤트 상태, 캠페인 상태) — 색상 매핑 근거
- `2-prd.md` (v1.4.0): 6장 플랫폼/UI(반응형 웹, 접근성 기준 미정의)
- `4-project-principle.md` (v1.5.0): 6장 프론트엔드 디렉토리 구조
- `7-execution-plan.md` (v1.0.1): SETUP-03(프로젝트 초기 셋업, 디자인 토큰 반영 작업)
- `8-wireframe.md` (v1.4.0): 화면별 레이아웃 구조 (본 스타일 가이드가 스타일을 입히는 대상)
- `report/db-schema-decisions-review.md`: `8-wireframe.md` 장 번호 변경(지점 등록 화면 제외) 근거
- `frontend/src/styles/tokens.css`: §2~§4 토큰의 실제 값
- `NH-Campaigner-UI-proposal.html` (저장소 루트): §2 CI 변수('개발 전달용'), §5.1 기록 버튼, §5.11·§5.14~5.16 컴포넌트의 근거 제안서
- NH뱅크 인터넷뱅킹 화면 캡처 (사용자 제공, 2026-09-08): §1 디자인 톤, §5.1/5.3/5.7/5.8 컴포넌트(pill 버튼, outline 배지, 탭 밑줄, 상단 유틸리티 바)의 시각 참고 자료. 문서로 보관되어 있지 않다

---

## 9. 미확정 사항 — 구현 전 확인 필요

- **§2 CI 색상 값의 정확도**: `--nh-human-blue #0066B3`·`--nh-nature-green #1FB25A`·`--nh-heart-yellow #FFC20E`와 파생값(`--primary-strong`, `--primary-tint`, `--ink*`, `--status-*`)은 `NH-Campaigner-UI-proposal.html`의 '개발 전달용' 화면 값이다. **CI 값은 사내 매뉴얼로 최종 확인이 필요하다.** v1.4.0까지의 NH 그린 근사값(`#00a651`)은 더 이상 쓰지 않는다.
- **시맨틱 색과 주색의 구분**: `--color-info`(`#2a5c8a`)는 그린 주색 시절 값 그대로라 Human Blue 주색과 같은 청색 계열이 되었다. 정보 배너와 주색 요소가 혼동되지 않는지 재검토가 필요하다.
- **토큰 외 직접 값**: 제안서 반영 컴포넌트 CSS가 토큰에 없는 크기·굵기·라운드(13px, 12.5px, 14.5px, 15px, 19px, 30px, 굵기 600, 라운드 3px·10px 등)와 hover 배경 `#f8fafc`를 직접 쓴다. 토큰으로 승격할지 결정이 필요하다.
- **NH 브랜드 시그니처 사용**: v1.4.0까지는 "NH뱅크 인터넷뱅킹의 로고·워드마크를 복제하지 않는다"는 전제였으나, 현재는 NH Campaigner 공식 시그니처(심볼+워드마크)를 상단 바·로그인에 그대로 쓰고 주색도 농협 CI로 맞췄다(§5.14). **상표·시그니처 사용 승인 여부는 확인이 필요하다.** 레이아웃은 NH뱅크 화면을 복제하지 않는다는 원칙은 유지한다.
