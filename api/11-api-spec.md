# 공공데이터 API 연동 명세 (인허가 · 국민연금)

- **버전**: v1.1.0
- **작성일**: 2026-10-01
- **관련 문서**: `docs/public data sources.md` (소스 전체 목록·키 관리 원칙)

**근거 자료**

| 자료 | 출처 |
|---|---|
| End Point · 요청변수 · 일일 한도 | data.go.kr 마이페이지 활용신청 상세 (2026-10-01 확인) |
| 호출 예시 | 행안부 공지 붙임1 `지방행정 인허가정보 API 호출 예` |
| 전체 195종 호출 URL | 행안부 공지 붙임2 `API 호출 URL 목록_20260727수정` |
| **응답 필드명** | 행안부 공지 붙임3 `제공항목(응답변수) 매핑테이블_20260727수정` |
| 업태구분명 | 행안부 공지 붙임4 `업종별 업태구분명_20260727신규` |
| 영업상태·자치단체 코드 | `개방자치단체코드_영업상태코드.xlsx` |
| 국민연금 | `국민연금공단_오픈API활용가이드_국민연금 가입 사업장 내역_v2.0.docx` |

> 아래 예시의 `{KEY}`는 `.env`의 `DATA_GO_KR_SERVICE_KEY` 값입니다. 이 문서에 실제 키를 적지 마십시오.

---

## 0. 한눈에 보기

| 구분 | 내용 |
|---|---|
| 승인 상태 | 전부 **승인** · 개발계정 · 자동승인 · 활용기간 2026-09-30 ~ 2028-09-30 |
| 인증키 | data.go.kr 계정 키 1개로 전부 호출 |
| 인허가 | **업종별 9개 API** × `/info` · `/history` |
| 국민연금 | 1개 API × 3개 오퍼레이션 |
| 일일 한도 | **오퍼레이션별 10,000회** |
| 1회 최대 행 | 인허가 **100행** |

**구 LOCALDATA(localdata.go.kr)는 2026-04-16 폐쇄됐습니다.** 신규 API는 요청·응답 이름이 전부 바뀌었습니다 (§1.8).

---

## 1. 지방행정 인허가 API

### 1.1 End Point

| 업종 | 업종코드 | End Point (뒤에 `/info` 또는 `/history`) |
|---|---|---|
| 일반음식점 | `07_24_04_P` | `https://apis.data.go.kr/1741000/general_restaurants` |
| 휴게음식점 | `07_24_05_P` | `https://apis.data.go.kr/1741000/rest_cafes` |
| 미용업 | `05_18_01_P` | `https://apis.data.go.kr/1741000/beauty_salons` |
| 통신판매업 | `08_26_04_P` | `https://apis.data.go.kr/1741000/ecommerce_businesses` |
| 의원 | `01_01_02_P` | `https://apis.data.go.kr/1741000/clinics` |
| 병원 | `01_01_01_P` | `https://apis.data.go.kr/1741000/hospitals` |
| 약국 | `01_01_06_P` | `https://apis.data.go.kr/1741000/pharmacies` |
| 숙박업 | `03_11_03_P` | `https://apis.data.go.kr/1741000/lodgings` |
| 체력단련장업 | `10_42_01_P` | `https://apis.data.go.kr/1741000/fitness_centers` |

- **업종 필터 = 호출하는 End Point**입니다. 전 업종을 한 번에 받는 API는 없습니다.
- 붙임2 목록은 `http://`로 적혀 있으나 마이페이지 End Point는 `https://`입니다. **https를 쓰십시오.**
- 나머지 186종 URL은 붙임2에 있습니다. 같은 `1741000/{영문명}/info|history` 패턴입니다.

### 1.2 오퍼레이션

| 경로 | 용도 | 갱신 |
|---|---|---|
| `/info` | 현재 데이터 | **매일 갱신, 2일 전(D-2) 기준 현행화** |
| `/history` | 과거 시점 데이터 | 데이터기준일자 **2026-01-01 ~ 조회일 전일** |

### 1.3 요청변수 (전부 선택 항목)

| 파라미터 | 설명 | 형식 | info | history |
|---|---|---|:---:|:---:|
| `serviceKey` | 인증키 | | ✅ | ✅ |
| `pageNo` | 페이지 번호 | | ✅ | ✅ |
| `numOfRows` | 한 페이지 결과 수 | **최대 100** | ✅ | ✅ |
| `returnType` | 응답 데이터 타입 | json / xml | ✅ | ✅ |
| `cond[DAT_UPDT_PNT::GTE]` / `::LT` | 데이터갱신시점 이상 / 미만 | **YYYYMMDDHHMMSS** | ✅ | ✅ |
| `cond[LCPMT_YMD::GTE]` / `::LT` | 인허가일자 이상 / 미만 | YYYYMMDD | ✅ | ✅ |
| `cond[SALS_STTS_CD::EQ]` | 영업상태코드 | §1.6 | ✅ | ✅ |
| `cond[OPN_ATMY_GRP_CD::EQ]` | 개방자치단체코드 | §1.7 | ✅ | ✅ |
| `cond[BPLC_NM::LIKE]` | 사업장명 포함 | | ✅ | ✅ |
| `cond[ROAD_NM_ADDR::LIKE]` | 도로명주소 포함 | | ✅ | — |
| `cond[BASE_DATE::EQ]` | 해당 기준일자 시점 상태 | YYYYMMDD | — | ✅ |

> `cond[...]`는 대괄호·콜론이 있어 URL 인코딩이 필요합니다. 파이썬 `requests`의 `params=`로 넘기면 자동 처리됩니다.

#### ⚠️ 변동분 기준 컬럼 선택: `DAT_UPDT_PNT` vs `LAST_MDFCN_PNT`

| 컬럼 | 바뀌는 경우 | 용도 |
|---|---|---|
| `DAT_UPDT_PNT` (데이터갱신시점) | 지자체 원천데이터 수정 **+ 개방 과정에서 추가된 정보(좌표 등) 수정** | 화면 표시 데이터 동기화 |
| `LAST_MDFCN_PNT` (최종수정시점) | **지자체 원천데이터 수정만** | ✅ **개업·폐업 신호 감지** |

행안부 붙임1이 명시한 내용입니다. **신호 감지에는 `cond[LAST_MDFCN_PNT::GTE]`를 쓰십시오.** `DAT_UPDT_PNT`로 받으면 좌표만 보정된 건까지 "변동"으로 잡혀 노이즈가 됩니다.

### 1.4 호출 예시

```
# ① 업종 전체 (병원)
https://apis.data.go.kr/1741000/hospitals/info?serviceKey={KEY}&pageNo=1&numOfRows=100

# ② 변동분 — 2026-03-01 00:00:00 이후
https://apis.data.go.kr/1741000/hospitals/info?serviceKey={KEY}&pageNo=1&numOfRows=100
  &cond[LAST_MDFCN_PNT::GTE]=20260301000000

# ③ 과거 시점 — 2026-01-01 기준 서울 종로구
https://apis.data.go.kr/1741000/hospitals/history?serviceKey={KEY}&pageNo=1&numOfRows=100
  &cond[BASE_DATE::EQ]=20260101&cond[OPN_ATMY_GRP_CD::EQ]=3000000
```

> 붙임1 ③ 예시에는 종로구 코드가 `30000000`(8자리)으로 적혀 있지만, 코드표와 매핑테이블(`CHAR 7`) 기준 **`3000000`(7자리)이 맞습니다.**

**파이썬 — 파일럿 지자체 변동분**

```python
import os, requests

URL = "https://apis.data.go.kr/1741000/general_restaurants/info"
params = {
    "serviceKey": os.getenv("DATA_GO_KR_SERVICE_KEY"),   # 디코딩키
    "pageNo": 1,
    "numOfRows": 100,
    "returnType": "json",
    "cond[OPN_ATMY_GRP_CD::EQ]": "3170000",              # 서울 금천구
    "cond[LAST_MDFCN_PNT::GTE]": "20260929000000",
}
r = requests.get(URL, params=params, timeout=30)
```

### 1.5 응답 필드 — 공통 (9개 업종 모두)

| 신규 필드 | 한글명 | 타입(길이) | 구 LOCALDATA | 우리 설계에서 |
|---|---|---|---|---|
| **`MNG_NO`** | 관리번호 | VARCHAR2(50) | `mgtNo` | **사업장 고유키** (BUSINESS 조인·중복제거) |
| `OPN_ATMY_GRP_CD` | 개방자치단체코드 | CHAR(7) | `opnSfTeamCode` | 지역 필터 |
| `DAT_UPDT_SE` | 데이터갱신구분 | CHAR(1) | `updateGbn` | |
| `DAT_UPDT_PNT` | 데이터갱신시점 | VARCHAR2(14) | `updateDt` | |
| **`LAST_MDFCN_PNT`** | 최종수정시점 | VARCHAR2(14) | `lastModTs` | **변동분 워터마크** |
| **`LCPMT_YMD`** | 인허가일자 | CHAR(8) | `apvPermYmd` | **신규 개업 신호** |
| `LCPMT_RTRCN_YMD` | 인허가취소일자 | CHAR(8) | `apvCancelYmd` | |
| **`SALS_STTS_CD`** | 영업상태코드 | VARCHAR2(20) | `trdStateGbn` | **배제 필터** (§1.6) |
| `SALS_STTS_NM` | 영업상태명 | VARCHAR2(300) | `trdStateNm` | |
| `DTL_SALS_STTS_CD` | 상세영업상태코드 | VARCHAR2(4) | `dtlStateGbn` | |
| `DTL_SALS_STTS_NM` | 상세영업상태명 | VARCHAR2(200) | `dtlStateNm` | |
| **`CLSBIZ_YMD`** | 폐업일자 | CHAR(8) | `dcbYmd` | **폐업 신호** |
| `TCBIZ_BGNG_YMD` | 휴업시작일자 | CHAR(8) | `clgStdt` | |
| `TCBIZ_END_YMD` | 휴업종료일자 | CHAR(8) | `clgEnddt` | |
| `ROBIZ_YMD` | 재개업일자 | CHAR(8) | `ropnYmd` | 재개업 신호 |
| **`BPLC_NM`** | 사업장명 | VARCHAR2(200) | `bplcNm` | 명부 표시 |
| `BZSTAT_SE_NM` | 업태구분명 | VARCHAR2(500) | `uptaeNm` | 세부 업종 (§1.9) |
| `TELNO` | 소재지전화번호 | VARCHAR2(11) | `siteTel` | |
| `LCTN_AREA` | 소재지면적 | VARCHAR2(18) | `siteArea` | 규모적합도 |
| `LCTN_ZIP` | 소재지우편번호 | CHAR(6) | `sitePostNo` | |
| `LOTNO_ADDR` | 지번주소 | VARCHAR2(200) | `siteWhlAddr` | |
| `ROAD_NM_ADDR` | 도로명주소 | VARCHAR2(200) | `rdnWhlAddr` | |
| `ROAD_NM_ZIP` | 도로명우편번호 | CHAR(5) | `rdnPostNo` | |
| **`CRD_INFO_X`** | 좌표X | CHAR(20) | `x` | 반경 매칭 (**EPSG:5174**) |
| **`CRD_INFO_Y`** | 좌표Y | CHAR(20) | `y` | 반경 매칭 (**EPSG:5174**) |

> 구 규격의 `opnSvcId`(개방서비스ID), `opnSvcNm`(개방서비스명)은 **삭제**됐습니다. 업종은 End Point로 구분합니다.

### 1.6 영업상태코드 (`SALS_STTS_CD`)

| 코드 | 명칭 | 배제 필터 (RULE-TARGET-01) |
|---|---|---|
| `01` | 영업/정상 | ✅ **명부 대상** |
| `02` | 휴업 | ❌ 배제 |
| `03` | 폐업 | ❌ 배제 · 폐업 신호 |
| `04` | 취소/말소/만료/정지/중지 | ❌ 배제 |
| `05` | 제외/삭제/전출 | ❌ 배제 |
| `06` | 기타 | ❌ 배제 |

### 1.7 개방자치단체코드 (`OPN_ATMY_GRP_CD`)

전체 261개는 `개방자치단체코드_영업상태코드.xlsx` 시트1에 있습니다.

| 형태 | 예시 | 의미 |
|---|---|---|
| `XXXXXXX_ALL` | `6110000_ALL` | 서울특별시 **전체** (광역 + 산하 시군구) |
| 광역 7자리 | `6110000` | 서울특별시 **본청** 처리분만 |
| 시군구 7자리 | `3170000` | 서울 금천구 |

**서울 자치구 (파일럿 후보 참고)**

| 자치구 | 코드 | 자치구 | 코드 | 자치구 | 코드 |
|---|---|---|---|---|---|
| 종로구 | 3000000 | 중구 | 3010000 | 용산구 | 3020000 |
| 성동구 | 3030000 | 광진구 | 3040000 | 동대문구 | 3050000 |
| 중랑구 | 3060000 | 성북구 | 3070000 | 강북구 | 3080000 |
| 도봉구 | 3090000 | 노원구 | 3100000 | 은평구 | 3110000 |
| 서대문구 | 3120000 | 마포구 | 3130000 | 양천구 | 3140000 |
| 강서구 | 3150000 | 구로구 | 3160000 | **금천구** | **3170000** |
| 영등포구 | 3180000 | 동작구 | 3190000 | 관악구 | 3200000 |
| 서초구 | 3210000 | **강남구** | **3220000** | 송파구 | 3230000 |
| 강동구 | 3240000 | | | | |

경기 성남시 = `3780000`

### 1.8 업종별 추가 응답 필드 (규모적합도에 쓸 만한 것)

공통 필드 외에 업종마다 추가 항목이 있습니다. 매핑테이블은 구 LOCALDATA **그룹** 기준이라, 붙임3 주석대로 *"같은 그룹이라도 업종에 따라 제공 여부가 달라질 수 있습니다."* **실제 제공 여부는 테스트 호출로 확인**하십시오.

| 업종 (매핑 그룹) | 규모 판단용 필드 |
|---|---|
| 일반·휴게음식점 (음식점) | `SEAT_CNT` 좌석수, `ML_PRCTR_CNT`·`FML_PRCTR_CNT` 남녀종사자수, `FCAR` 시설면적, `FCLT_TOTAL_SCL` 시설총규모, `MLT_UTZTN_BSNSSP_YN` 다중이용업소여부, `SNTTN_BZSTAT_NM` 위생업태명 |
| 미용업 (미용) | `CHAI_CNT` 좌석수, `BED_CNT` 침대수, 남녀종사자수 |
| 의원·병원·약국 (의료기관) | `HCWKR_CNT` 의료인수, `EMP_CNT` 직원수, `SCKBD_CNT` 병상수, `HSPTLZRM_CNT` 입원실수, `GFA` 총면적, `MDLCR_INST_BTP_NM` 의료기관종별명, `MDEXM_SBJCT_CN_NM` 진료과목, `PMCY_SALS_AREA` 약국영업면적 |
| 숙박업 (숙박) | `GSRM_CNT` 객실수, `ARCH_TFA` 건축연면적, `TOUR_LDGBIZ_DTL_NM` 관광숙박업상세명 |
| 체력단련장업 (체육) | `BDST_TFA` 건축물연면적, `LDER_CNT` 지도자수, `CORP_NM` 법인명, `MBR_RCRT_TOTAL_PERNE` 회원모집총인원 |
| 통신판매업 (유통 그룹으로 추정) | **`BRNO` 사업자등록번호**, `CPTL` 자본금, `AST_SCL` 자산규모, `NTSL_MTH_NM` 판매방식명 |

#### ❌ 통신판매업에 사업자등록번호(`BRNO`)는 오지 않습니다 (2026-10-07 실호출)

매핑테이블의 유통 그룹에는 `BRNO`가 있지만, 통신판매업 API 응답(전국 100건, 강남구 변동분 100건)에 **필드 자체가 없었습니다.** 국세청 사업자상태조회 API를 연계할 사업자번호 경로는 여전히 없습니다(`public data sources.md` S-8). 휴폐업 배제는 인허가 영업상태(1차)로 처리합니다.

**실제 응답에서 문서와 다른 필드** — 숙박업 객실수는 `GSRM_CNT`가 아니라 `KSRM_CNT`·`WSRM_CNT`로 옵니다. 일반음식점 응답에는 `SEAT_CNT`·`FCAR`이 없습니다.

### 1.9 업태구분명 (`BZSTAT_SE_NM`)

같은 업종 안의 세부 유형입니다. 신호×업종 가중치(SIGNAL_WEIGHT)를 더 잘게 나눌 때 씁니다. 전체 목록은 붙임4에 있습니다.

| 업종 | 업태구분명 |
|---|---|
| 일반음식점 (36종) | 한식, 중국식, 경양식, 일식, 분식, 뷔페식, 호프/통닭, 통닭(치킨), 김밥(도시락), 횟집, 까페, 커피숍, 패스트푸드, 키즈카페, 푸드트럭, 제과점영업 외 |
| 휴게음식점 (31종) | 커피숍, 까페, 분식, 패스트푸드, 아이스크림, **편의점**, 백화점, 고속도로, 철도역구내, 키즈카페, 푸드트럭 외 |
| 미용업 (7종) | 일반미용업, 피부미용업, 네일아트업, 메이크업업, 일반이용업, 기타 |
| 의원 (8종) | 의원, 치과의원, 한의원, 조산원, 보건소, 보건지소, 보건진료소, 보건의료원 |
| 병원 (8종) | 병원, 종합병원, 한방병원, 치과병원, 요양병원(3종), 정신병원 |
| 숙박업 (7종) | 관광호텔, 일반호텔, 휴양콘도미니엄업, 여관업, 여인숙업, 숙박업(생활), 기타 |
| 통신판매업 (12종) | 종합몰, 가전, 컴퓨터/사무용품, 의류/패션/잡화/뷰티, 건강/식품, 레져/여행/공연, 상품권 외 |

> 의원 업태에 **보건소·보건지소**가 섞여 있습니다. 공공기관이라 영업 대상이 아니므로 **배제 필터에 추가**하십시오.

### 1.10 구 LOCALDATA → 신규 API 변경 대조

| 항목 | 구 LOCALDATA (폐쇄) | 신규 API |
|---|---|---|
| End Point | 단일 API + 업종코드 | **업종별 End Point** |
| 변동분 파라미터 | `lastModTsBgn` / `lastModTsEnd` | `cond[LAST_MDFCN_PNT::GTE]` / `::LT` |
| 변동분 형식 | YYYYMMDD | **YYYYMMDDHHMMSS** |
| 페이징 | `pageIndex` + `pageSize` | `pageNo` + `numOfRows` |
| 1회 최대 | (가정 500행) | **100행** |
| 응답 타입 | `resultType` | `returnType` |
| 응답 필드 | camelCase (`mgtNo`, `bplcNm`, `trdStateGbn` …) | **대문자 스네이크** (`MNG_NO`, `BPLC_NM`, `SALS_STTS_CD` …) — §1.5 |

### 1.11 호출량 계산

| 시나리오 | 계산 | 판단 |
|---|---|---|
| 파일럿 지자체 변동분 × 9업종 | 지자체 하루 변동분은 업종당 수십 건 수준 → 업종당 1~수 회 | ✅ 여유 |
| 하루 200회 상한 | 200회 × 100행 = 업종당 **2만 행** | ✅ 변동분에 충분 |
| 파일럿 지자체 모집단 최초 적재 | 지자체·업종당 수천 건 ÷ 100 = 수십 회 | ✅ 가능 |
| 전국 전수 (일반음식점) | 수십만 건 ÷ 100 = **수천 회** | ⚠️ 한도에 근접. 비권장 |

**전국 전수는 API로 받지 마십시오.** 파일럿 지자체 코드로 걸러 받거나 data.go.kr 표준데이터 CSV를 쓰십시오.

### 1.12 배치 설계 메모

- **D-2 지연**이 있으므로 "어제 날짜" 고정 조회는 누락이 생깁니다. 마지막 성공 시점의 `LAST_MDFCN_PNT`를 워터마크로 저장하고, 1일을 겹쳐 조회한 뒤 **`MNG_NO`로 중복 제거**하십시오.
- **좌표는 EPSG:5174** (보정계수 미적용 Bessel 중부원점TM)입니다. `CRD_INFO_X/Y`를 WGS84로 변환해 저장하십시오 (VAL-11). 값이 문자열(CHAR 20)이니 숫자 변환과 빈 값 처리가 필요합니다.
- **신규 개업**은 `LCPMT_YMD`가 최근 N일, **폐업**은 `SALS_STTS_CD = 03` 이면서 `CLSBIZ_YMD`가 최근 N일인 건입니다.
- **`/history`는 백테스트용**입니다. 2026-01-01 이후 임의 시점의 상태를 재현할 수 있습니다.

### 1.13 테스트 호출로 확인할 것 (1회면 됨)

매핑테이블로 필드명은 확정됐습니다. 남은 건 실제 응답에서만 보이는 것들입니다.

2026-10-07 EC2에서 9개 업종 실호출로 확인했습니다.

- [x] 응답 JSON 구조 — `response.body.items.item[]`. **정상 `resultCode`는 `"0"`** (구 표준 `"00"` 아님)
- [x] `returnType=json` 허용
- [x] 통신판매업 `BRNO` — **없음** (§1.8)
- [x] 업종별 추가 필드 — §1.8 주석 참고
- [x] `numOfRows`를 100보다 크게 요청하면 **오류 없이 100행만** 온다 → 페이지 종료는 `totalCount`로 판단
- [x] 1회 호출 20초~2분 (전국 무필터 기준). 공통 HTTP 타임아웃(15초)으로는 끊긴다 → 인허가는 90초

---

## 2. 국민연금 가입 사업장 내역 API

### 2.1 기본 정보

| 항목 | 값 |
|---|---|
| End Point | `https://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2` |
| 응답 타입 파라미터 | **`dataType`** (json / xml, 기본 xml) — 인허가의 `returnType`과 **이름이 다름** |
| 응답 구조 | `response.body.items.item[]` |
| 요청 표기 | camelCase (2025-05-07 개편, 이전 snake_case 폐기) |
| 데이터 제공 | 매월 **15일 이후** 전월분 반영 |
| API 보관 기간 | **제공 시점 기준 1년치만** |
| 일일 한도 | 오퍼레이션별 10,000회 |

### 2.2 오퍼레이션

| 경로 | 용도 | 필수 입력 | 주요 응답 |
|---|---|---|---|
| `/getBassInfoSearchV2` | 사업장 목록 검색 | **`wkplNm`(사업장명) 또는 `bzowrRgstNo`(사업자번호 앞 6자리)** | `seq`, `dataCrtYm`, `wkplNm`, `wkplRoadNmDtlAddr`, `wkplJnngStcd`, 법정동코드 3종 |
| `/getDetailInfoSearchV2` | 사업장 1건 상세 | `seq` | **`jnngpCnt` 가입자수**, `wkplIntpCd`·`vldtVlKrnNm` 업종, `adptDt` 등록일, `scsnDt` 탈퇴일, `crrmmNtcAmt` 고지금액 |
| `/getPdAcctoSttusInfoSearchV2` | 사업장 1건 월별 증감 | `seq` (+ `dataCrtYm` YYYYMM) | `nwAcqzrCnt` 취업자수, `lssJnngpCnt` 퇴직자수 |

**목록조회 요청변수**: `ldongAddrMgplDgCd`(시도), `ldongAddrMgplSgguCd`(시군구), `ldongAddrMgplSgguEmdCd`(읍면동), `wkplNm`, `bzowrRgstNo`, `dataType`, `pageNo`, `numOfRows`, `serviceKey`

### 2.3 ⚠️ 설계를 가르는 제약

1. **지역 전수 조회가 안 됩니다.** 목록조회는 사업장명이나 사업자번호를 넣어야 동작합니다. "가산동 사업장 전부"는 불가능합니다.
2. **가입자수는 상세조회에만 있습니다.** 사업장마다 상세조회, 월별 증감은 또 별도 호출 → **사업장 1개당 2~3회**입니다.
3. **`seq`는 월마다 바뀔 수 있습니다.** 가이드에 "월별 누적데이터로 조회시점에 따라 누적식별번호 표출"로 되어 있어, 월을 넘긴 추적 키로는 불안정합니다.
4. **1년치만 보관합니다.** 백테스트용 과거 데이터는 API로 못 받습니다.

### 2.4 결론 — 파일이 주력, API는 보조

| 용도 | 수단 |
|---|---|
| 법인 모집단 · 신설 법인 · 인력 증감 신호 | **CSV 파일** (월 1회, 59만 건, 키 불필요) |
| 백테스트 (과거 시점) | **CSV 파일** (주기성 과거 데이터 약 128개월) |
| 명부에 오른 특정 기업의 최신 상세 | API (`getBass` → `getDetail`) |

정제 규칙(`일용` 제외, 가입자수 5~500명, 탈퇴 배제 등)과 월간 조인 키는 `10-data-sources.md` §3 F-1을 따릅니다.

---

## 3. 남은 확인 사항

| # | 할 일 | 담당 |
|---|---|---|
| 1 | ~~인허가 테스트 호출 1회 → §1.13 체크리스트 확인~~ | ✅ 2026-10-07 |
| 2 | ~~통신판매업 `BRNO` 제공 여부~~ → **미제공**. 국세청 연계 불가 | ✅ 2026-10-07 |
| 3 | 파일럿 지자체 `OPN_ATMY_GRP_CD` — 지점 5곳 + 반경이 걸치는 인접 구로 `pipeline.toml` `region_codes`에 설정. 기획 확정 필요 | 기획 |
| 4 | ~~배제 필터에 의원 업태 `보건소·보건지소·보건진료소·보건의료원` 추가~~ → `pipeline.toml` `[exclusion] excluded_permit_keywords` | ✅ 2026-10-07 |
| 5 | ~~약국·체력단련장업의 구 개방서비스ID 확인 → `pipeline.toml` `service_id` 교체~~ → 약국 `01_01_06_P`, 체력단련장업 `10_42_01_P`(서울 열린데이터광장 `LOCALDATA_010106`·`LOCALDATA_104201` 실호출로 확인). 기존 DB는 `backend/database/patches/2026-10-14_permit_service_ids.sql` | ✅ 2026-10-14 |

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.0.0 | 2026-10-01 | 최초 작성. 인허가 9종·국민연금 API 명세 |
| v1.1.0 | 2026-10-01 | 행안부 공지 붙임1~4 반영. 응답 필드명 확정(§1.5), 변동분 기준을 `LAST_MDFCN_PNT`로 변경(§1.3), 업종별 추가 필드·업태구분명 추가(§1.8~1.9), 통신판매업 `BRNO` 가능성 기록 |
| v1.2.0 | 2026-10-07 | EC2 실호출 결과 반영(§1.13): `resultCode "0"`, 100행 상한 무음 절단, 통신판매업 `BRNO` 미제공, 숙박 객실수 필드명. 커넥터 적용(`permit_connector.py`) 및 §3 갱신 |
