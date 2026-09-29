"""정규화·좌표 변환·인허가 파싱 단위 테스트 (VAL-09, VAL-11, RULE-SENSE-03)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.batch.normalizers import signal_normalizer as normalizer
from backend.batch.normalizers.permit_parser import map_operating_status, parse_permit_row
from backend.batch.population.business_loader import permit_to_record, sbiz_item_to_record
from backend.common.config import get_pipeline_config
from backend.common.geo import extract_sido, haversine_km, to_wgs84
from backend.tests.factories import TODAY, branch

CONFIG = get_pipeline_config()


def test_epsg5174_conversion_lands_in_seoul():
    # 중부원점(false easting 200000, false northing 500000) 남쪽 50km ≈ 서울 도심
    lat, lng = to_wgs84(200000, 450000, "EPSG:5174")
    assert 37.5 < lat < 37.6
    assert 126.95 < lng < 127.05


def test_out_of_korea_coordinates_are_rejected():
    assert to_wgs84(-900000, 0, "EPSG:5174") is None
    assert to_wgs84(139.7, 35.6, "EPSG:4326") is None  # 도쿄


def test_zero_permit_coordinates_are_not_loaded():
    permit = parse_permit_row({"관리번호": "A-1", "사업장명": "예시", "영업상태구분코드": "01",
                               "좌표정보(x)": "0", "좌표정보(y)": "0"})
    assert permit is not None
    assert permit_to_record(permit, TODAY) is None


def test_haversine_and_sido():
    assert haversine_km(37.5, 127.0, 37.5, 127.0) == 0
    assert haversine_km(37.5, 127.0, 37.509, 127.0) == pytest.approx(1.0, abs=0.01)
    assert extract_sido("서울특별시 강남구 테헤란로 152") == "서울"
    assert extract_sido("경기도 성남시") == "경기"
    assert extract_sido(None) is None


@pytest.mark.parametrize(("code", "name", "detail", "expected"), [
    ("01", "영업/정상", "영업", "정상"),
    ("02", "휴업", "휴업", "휴업"),
    ("03", "폐업", "폐업", "폐업"),
    ("04", "취소/말소/만료/정지/중지", "말소", "폐업"),
    ("01", "영업/정상", "영업정지", "영업정지"),
    ("", "", "", None),
])
def test_permit_status_mapping(code, name, detail, expected):
    assert map_operating_status(code, name, detail) == expected


def test_parse_permit_row_from_csv_columns_and_convert():
    row = {"개방서비스아이디": "07_24_04_P", "개방서비스명": "일반음식점", "관리번호": "3220000-101-2026-00001",
           "사업장명": "예시분식", "영업상태구분코드": "01", "영업상태명": "영업/정상", "상세영업상태명": "영업",
           "인허가일자": "2026-09-20", "업태구분명": "분식", "좌표정보(x)": "203500.0", "좌표정보(y)": "445000.0",
           "도로명전체주소": "서울특별시 강남구 예시로 1"}
    permit = parse_permit_row(row)
    assert permit is not None
    assert permit.mgt_no == "07_24_04_P-3220000-101-2026-00001"
    assert permit.industry_name == "일반음식점·분식"
    assert permit.licensed_on == date(2026, 9, 20)
    record = permit_to_record(permit, date(2026, 9, 1))
    assert record is not None and record.source_crs == "EPSG:5174"
    assert 37.4 < record.lat < 37.6


def test_parse_permit_row_from_api_fields():
    row = {"mgtNo": "M-1", "opnSvcId": "07_24_04_P", "opnSvcNm": "일반음식점", "bplcNm": "예시식당",
           "trdStateGbn": "03", "trdStateNm": "폐업", "dcbYmd": "20260927"}
    permit = parse_permit_row(row)
    assert permit is not None and permit.operating_status == "폐업" and permit.closed_on == date(2026, 9, 27)
    assert permit_to_record(permit, TODAY) is None  # 좌표 없음 → 상태 갱신만


def test_sbiz_item_mapping_keeps_wgs84():
    item = {"bizesId": "MA0101", "bizesNm": "예시카페", "brchNm": "역삼점", "indsLclsNm": "음식", "indsMclsNm": "비알코올",
            "indsSclsNm": "카페", "indsSclsCd": "I21201", "rdnmAdr": "서울특별시 강남구 예시로 2", "lon": "127.036",
            "lat": "37.501"}
    record = sbiz_item_to_record(item, date(2026, 9, 1))
    assert record is not None
    assert record.name == "예시카페 역삼점" and record.industry_name == "음식·비알코올·카페"
    assert record.source_crs == "EPSG:4326" and record.status_source == "SBIZ"


def test_permit_openings_produce_business_industry_area_signals():
    b = branch()
    openings = [
        normalizer.OpeningInfo(1, "예시분식", "일반음식점", date(2026, 9, 25), 37.501, 127.036),
        normalizer.OpeningInfo(2, "예시식당", "일반음식점", date(2026, 9, 26), 37.502, 127.037),
        normalizer.OpeningInfo(3, "먼곳상점", "일반음식점", date(2026, 9, 26), 37.60, 127.20),  # 반경 밖
    ]
    signals = normalizer.normalize_permit_openings(b, openings, snapshot_id=9, as_of_date=date(2026, 9, 27),
                                                   config=CONFIG.normalization)
    by_type = {}
    for s in signals:
        by_type.setdefault(s.signal_type, []).append(s)
    assert {s.business_id for s in by_type["NEW_BUSINESS_OPENING"]} == {1, 2}
    [area] = by_type["AREA_NEW_OPENINGS"]
    assert area.raw_value == 2 and area.scope == "AREA"
    [industry] = by_type["INDUSTRY_NEW_OPENINGS"]
    assert industry.target_key == "INDUSTRY:일반음식점" and industry.industry_name == "일반음식점"
    assert all(s.as_of_date == date(2026, 9, 27) for s in signals)  # VAL-09


def test_weather_warning_latest_action_wins_and_release_is_stored_as_zero():
    payload = {"stations": {"109": [
        {"title": "[특보] 제09-01호 : 2026.09.28.10:00 / 호우주의보 발효(*)", "tmFc": "202609281000", "tmSeq": 1},
        {"title": "[특보] 제09-02호 : 2026.09.29.06:00 / 호우주의보 해제, 강풍주의보 발효", "tmFc": "202609290600",
         "tmSeq": 2},
    ]}}
    signals = {s.target_key: s for s in normalizer.normalize_weather_warnings(branch(), payload, snapshot_id=1,
                                                                            config=CONFIG)}
    assert signals["WEATHER:호우주의보"].raw_value == 0 and signals["WEATHER:호우주의보"].intensity == 0
    assert signals["WEATHER:강풍주의보"].raw_value == 1
    assert signals["WEATHER:강풍주의보"].as_of_date == TODAY


def test_fx_change_uses_latest_two_business_days():
    payload = {"rows": [{"TIME": "20260925", "DATA_VALUE": "1,380.00"}, {"TIME": "20260928", "DATA_VALUE": "1397.25"},
                        {"TIME": "20260924", "DATA_VALUE": "1370.00"}]}
    fx = normalizer.compute_fx_change(payload)
    assert fx is not None and fx["as_of"] == date(2026, 9, 28)
    assert fx["change_pct"] == pytest.approx(1.25, abs=1e-3)
    [signal] = normalizer.normalize_fx(branch(), fx, snapshot_id=1, config=CONFIG.normalization)
    assert signal.raw_value == pytest.approx(1.25, abs=1e-3) and signal.unit == "%"


def test_oil_price_change_maps_branch_sido():
    payload = {"prodcd": "B027", "oil": [{"SIDOCD": "01", "PRICE": "1700", "DIFF": "17"},
                                         {"SIDOCD": "02", "PRICE": "1650", "DIFF": "-5"}]}
    [signal] = normalizer.normalize_oil_price(branch(), payload, snapshot_id=1, as_of_date=TODAY, config=CONFIG)
    assert signal.detail["sido"] == "서울"
    assert signal.raw_value == pytest.approx(17 / 1683 * 100, abs=1e-3)
