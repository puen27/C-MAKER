"""개발용 픽스처 적재 — 공공데이터 인증키 없이 로컬에서 파이프라인 전체를 확인하기 위한 데이터.

⚠ APP_ENV=dev 에서만 실행된다. 운영 DB에 쓰지 않는다.
   - 모든 상호명은 실제 사업자와 무관한 가상 예시명이다(개인정보 없음).
   - 스냅샷은 request_params.dev_fixture=true 로 표시된다.

적재 내용 (seed.sql 이후 실행)
1. 지점 000101의 좌표를 채우고 효력 시각을 과거로 당긴다(지오코딩 키가 없는 로컬 환경 대체)
2. 지점 반경 안 가상 사업체 30곳 (상가정보·인허가 출처 혼합, 휴·폐업 2곳 포함 → 배제 확인용)
3. 과거 기준일 원본 스냅샷 4종(인허가 변동분·기상특보·ECOS·오피넷)
   → 인증키가 없으면 커넥터가 실패하고 이 스냅샷으로 폴백하므로, 지연 배지(RULE-SENSE-04)까지 확인된다.

실행: APP_ENV=dev python -m backend.scripts.load_dev_fixture
제거: APP_ENV=dev python -m backend.scripts.clear_dev_fixture (배치 결과까지 함께 지운다)
"""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta

from pyproj import Transformer

from backend.common.config import get_settings, today_kst
from backend.common.db.pool import close_pool, get_connection
from backend.common.snapshot_store import save_snapshot

BRANCH_CODE = "000101"
BRANCH_LAT, BRANCH_LNG = 37.5000, 127.0364  # 서울 강남구 테헤란로 152 부근

# (업종명, 업종코드, 상호 접두)
INDUSTRIES = [
    ("음식·한식·백반/한정식", "I20101", "예시한식당"),
    ("음식·분식·김밥/만두/분식", "I21001", "예시분식"),
    ("음식·비알코올·카페", "I21201", "예시카페"),
    ("소매·종합 소매·편의점", "G20405", "예시편의점"),
    ("보건의료·의약·약국", "Q10201", "예시약국"),
    ("수리·개인·세탁·세탁소", "S20701", "예시세탁소"),
    ("수리·개인·미용·미용실", "S20901", "예시미용실"),
    ("교육·일반 교습 학원·외국어학원", "P10501", "예시어학원"),
    ("부동산·부동산 서비스·부동산 중개", "L10201", "예시공인중개"),
    ("숙박·일반 숙박·여행사", "N10101", "예시여행사"),
]

_TO_5174 = Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)


def _offset(index: int, radius_km: float) -> tuple[float, float]:
    """지점 중심에서 결정론적으로 흩어진 좌표(반경의 90% 이내)."""
    angle = (index * 137.508) % 360  # 황금각 분포
    distance = radius_km * 0.9 * math.sqrt((index + 1) / 32)
    d_lat = distance / 111.32 * math.cos(math.radians(angle))
    d_lng = distance / (111.32 * math.cos(math.radians(BRANCH_LAT))) * math.sin(math.radians(angle))
    return round(BRANCH_LAT + d_lat, 7), round(BRANCH_LNG + d_lng, 7)


def load_branch(conn) -> None:
    # 트리거(CONST-19)는 좌표 갱신을 다음 날 07:30부터 반영한다. 로컬 확인을 위해 개발 환경에서만
    # 트리거를 잠시 끄고 효력 시각을 과거로 둔다.
    conn.execute("ALTER TABLE branch DISABLE TRIGGER trg_branch_effective_from")
    conn.execute(
        """
        UPDATE branch SET lat = %s, lng = %s, geocoded_address = address,
               effective_from = now() - interval '1 day'
        WHERE branch_code = %s
        """,
        (BRANCH_LAT, BRANCH_LNG, BRANCH_CODE),
    )
    conn.execute("ALTER TABLE branch ENABLE TRIGGER trg_branch_effective_from")


def load_businesses(conn, population_as_of: date, today: date) -> int:
    count = 0
    for index in range(30):
        industry_name, industry_code, prefix = INDUSTRIES[index % len(INDUSTRIES)]
        lat, lng = _offset(index, 1.5)
        status = "폐업" if index == 7 else "휴업" if index == 13 else "정상"
        permit_sourced = index % 3 == 0
        licensed_on = today - timedelta(days=20 + index * 11) if permit_sourced else None
        conn.execute(
            """
            INSERT INTO business (permit_mgt_no, sbiz_store_id, name, industry_code, industry_name, address, lat, lng,
                                  source_crs, operating_status, status_source, licensed_on, status_checked_at,
                                  population_as_of)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                f"07_24_04_P-DEV-P-{index:04d}" if permit_sourced else None,
                None if permit_sourced else f"DEV-S-{index:04d}",
                f"{prefix} {index + 1:02d}호점(개발용)",
                industry_code,
                industry_name,
                f"서울특별시 강남구 예시로 {index + 1}",
                lat,
                lng,
                "EPSG:5174" if permit_sourced else "EPSG:4326",
                status,
                "PERMIT" if permit_sourced else "SBIZ",
                licensed_on,
                population_as_of,
                population_as_of,
            ),
        )
        count += 1
    return count


def load_snapshots(conn, today: date) -> dict[str, int]:
    params = {"dev_fixture": True}
    ids: dict[str, int] = {}

    # 인허가 변동분 — 기대 기준일(D-2)보다 하루 늦은 D-3 원본: 신규 개업 4건 + 기존 사업체 폐업 1건
    change_date = today - timedelta(days=3)
    rows = []
    for number in range(4):
        lat, lng = _offset(40 + number, 1.2)
        x, y = _TO_5174.transform(lng, lat)
        rows.append({
            "opnSvcId": "07_24_04_P", "opnSvcNm": "일반음식점" if number < 2 else "휴게음식점",
            "mgtNo": f"DEV-N-{change_date:%Y%m%d}-{number}", "bplcNm": f"예시신규점 {number + 1}(개발용)",
            "trdStateGbn": "01", "trdStateNm": "영업/정상", "dtlStateNm": "영업",
            "apvPermYmd": (change_date - timedelta(days=number)).strftime("%Y%m%d"),
            "x": round(x, 3), "y": round(y, 3), "rdnWhlAddr": f"서울특별시 강남구 예시신규로 {number + 1}",
            "uptaeNm": "한식" if number < 2 else "커피숍", "updateGbn": "I",
        })
    rows.append({"opnSvcId": "07_24_04_P", "opnSvcNm": "일반음식점", "mgtNo": "DEV-P-0003",
                 "bplcNm": "예시편의점 04호점(개발용)", "trdStateGbn": "03", "trdStateNm": "폐업",
                 "dcbYmd": change_date.strftime("%Y%m%d"), "updateGbn": "U"})
    ids["PERMIT_DAILY"] = save_snapshot(conn, "PERMIT_DAILY", change_date,
                                        {"change_date": change_date.isoformat(), "rows": rows}, params)

    # 기상특보 — 전일 폭염주의보 발효(서울 관할 109)
    yesterday = today - timedelta(days=1)
    ids["KMA_WARNING"] = save_snapshot(conn, "KMA_WARNING", yesterday, {
        "target_date": yesterday.isoformat(),
        "stations": {"109": [{"stnId": 109, "tmSeq": 1, "tmFc": f"{yesterday:%Y%m%d}1000",
                              "title": f"[특보] 제01-01호 : {yesterday:%Y.%m.%d}.10:00 / 폭염주의보 발효(*)"}]},
    }, params)

    # ECOS 원/달러 — 직전 두 영업일 +1.30%
    ecos_day = today - timedelta(days=2)
    ids["ECOS_FX"] = save_snapshot(conn, "ECOS_FX", ecos_day, {"rows": [
        {"TIME": (ecos_day - timedelta(days=1)).strftime("%Y%m%d"), "DATA_VALUE": "1380.00"},
        {"TIME": ecos_day.strftime("%Y%m%d"), "DATA_VALUE": "1397.94"},
    ]}, params)

    # 오피넷 시도별 휘발유 — 서울 +0.80%
    ids["OPINET_PRICE"] = save_snapshot(conn, "OPINET_PRICE", yesterday, {"prodcd": "B027", "oil": [
        {"SIDOCD": "01", "SIDONM": "서울", "PRODCD": "B027", "PRICE": "1764.10", "DIFF": "14.00"},
    ]}, params)
    return ids


def main() -> int:
    settings = get_settings()
    if not settings.is_dev:
        print("APP_ENV=dev 에서만 실행할 수 있습니다(운영 DB 보호).", file=sys.stderr)
        return 2
    today = today_kst()
    try:
        with get_connection() as conn:
            branch = conn.execute("SELECT id FROM branch WHERE branch_code = %s", (BRANCH_CODE,)).fetchone()
            if branch is None:
                print("seed.sql을 먼저 적용하세요(지점 000101 없음).", file=sys.stderr)
                return 1
            load_branch(conn)
            businesses = load_businesses(conn, today.replace(day=1), today)
            snapshots = load_snapshots(conn, today)
        print(f"개발용 픽스처 적재 완료: 사업체 {businesses}곳, 스냅샷 {snapshots}")
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
