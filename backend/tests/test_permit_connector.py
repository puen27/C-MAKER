"""업종별 인허가 API(S-10~S-18) 커넥터·파서·변동분 창 테스트 (api/11-api-spec.md §1)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.batch import run_daily
from backend.batch.connectors import permit_connector
from backend.batch.connectors.http_client import SourceFetchError
from backend.batch.normalizers.permit_parser import is_excluded_permit, map_operating_status, parse_permit_row
from backend.common.config import get_pipeline_config

CONFIG = get_pipeline_config()
RESTAURANT = permit_connector.PermitService("07_24_04_P", "일반음식점", "general_restaurants")
CLINIC = permit_connector.PermitService("01_01_02_P", "의원", "clinics")
WINDOW = (datetime(2026, 10, 4), datetime(2026, 10, 7))


def _page(items, total, code="0"):
    return {"response": {"header": {"resultCode": code, "resultMsg": "정상"},
                         "body": {"items": {"item": items}, "totalCount": total, "numOfRows": 100, "pageNo": 1}}}


def _row(mng_no, modified="2026-10-05 04:15:10", **extra):
    return {"MNG_NO": mng_no, "BPLC_NM": f"사업장{mng_no}", "SALS_STTS_CD": "01", "SALS_STTS_NM": "영업/정상",
            "LAST_MDFCN_PNT": modified, **extra}


def test_new_api_params_paging_and_service_tagging(monkeypatch):
    calls = []
    pages = {1: _page([_row("A"), _row("B")], 3), 2: _page([_row("C")], 3)}

    def fake_request(method, url, *, params=None, timeout=None, **_):
        calls.append((url, dict(params), timeout))
        return pages[params["pageNo"]]

    monkeypatch.setattr(permit_connector, "request_json", fake_request)
    result = permit_connector.fetch_daily_changes(
        "KEY", "https://apis.data.go.kr/1741000/", [RESTAURANT], *WINDOW, region_codes=["3010000"], timeout=90,
    )

    url, params, timeout = calls[0]
    assert url == "https://apis.data.go.kr/1741000/general_restaurants/info"
    assert params["cond[LAST_MDFCN_PNT::GTE]"] == "20261004000000"
    assert params["cond[LAST_MDFCN_PNT::LT]"] == "20261007000000"
    assert params["cond[OPN_ATMY_GRP_CD::EQ]"] == "3010000"
    assert params["numOfRows"] == 100 and params["returnType"] == "json"
    assert not {"lastModTsBgn", "pageIndex", "pageSize", "resultType"} & params.keys()
    assert timeout == 90
    assert [c[1]["pageNo"] for c in calls] == [1, 2]

    rows = result.payload["rows"]
    assert [r["MNG_NO"] for r in rows] == ["A", "B", "C"]
    assert all(r["opnSvcId"] == "07_24_04_P" and r["opnSvcNm"] == "일반음식점" for r in rows)
    assert result.payload["window"] == {"from": "20261004000000", "to": "20261007000000"}
    assert "KEY" not in str(result.request_params)


def test_truncated_pages_follow_total_count(monkeypatch):
    """numOfRows를 크게 줘도 100행만 오는 API — 받은 행 수가 아니라 totalCount까지 넘긴다."""
    pages = {1: _page([_row(f"R{i}") for i in range(100)], 150), 2: _page([_row(f"S{i}") for i in range(50)], 150)}
    monkeypatch.setattr(permit_connector, "request_json", lambda *a, params=None, **k: pages[params["pageNo"]])
    result = permit_connector.fetch_daily_changes("KEY", "https://x", [RESTAURANT], *WINDOW, page_size=500)
    assert len(result.payload["rows"]) == 150


def test_dedup_keeps_latest_modification_per_service(monkeypatch):
    by_region = {
        "R1": _page([_row("A", "2026-10-04 10:00:00"), _row("B")], 2),
        "R2": _page([_row("A", "2026-10-05 09:00:00", SALS_STTS_CD="03")], 1),
    }
    monkeypatch.setattr(
        permit_connector, "request_json",
        lambda *a, params=None, **k: by_region[params["cond[OPN_ATMY_GRP_CD::EQ]"]],
    )
    result = permit_connector.fetch_daily_changes("KEY", "https://x", [RESTAURANT], *WINDOW, region_codes=["R1", "R2"])
    rows = {r["MNG_NO"]: r for r in result.payload["rows"]}
    assert set(rows) == {"A", "B"}
    assert rows["A"]["SALS_STTS_CD"] == "03"


def test_same_mng_no_in_different_services_is_kept(monkeypatch):
    monkeypatch.setattr(permit_connector, "request_json", lambda *a, **k: _page([_row("A")], 1))
    result = permit_connector.fetch_daily_changes("KEY", "https://x", [RESTAURANT, CLINIC], *WINDOW, max_workers=2)
    assert sorted(r["opnSvcId"] for r in result.payload["rows"]) == ["01_01_02_P", "07_24_04_P"]


@pytest.mark.parametrize("code,expected", [("0", 1), ("00", 1), ("03", 0)])
def test_result_codes(monkeypatch, code, expected):
    payload = _page([_row("A")], 1, code=code)
    monkeypatch.setattr(permit_connector, "request_json", lambda *a, **k: payload)
    result = permit_connector.fetch_daily_changes("KEY", "https://x", [RESTAURANT], *WINDOW)
    assert len(result.payload["rows"]) == expected


def test_error_code_fails_whole_fetch(monkeypatch):
    """한 업종이라도 실패하면 전체 실패 — 일부만 저장하면 다음 창이 그 업종 누락분을 건너뛴다."""

    def fake_request(method, url, **_):
        return _page([], 0, code="30") if "clinics" in url else _page([_row("A")], 1)

    monkeypatch.setattr(permit_connector, "request_json", fake_request)
    with pytest.raises(SourceFetchError):
        permit_connector.fetch_daily_changes("KEY", "https://x", [RESTAURANT, CLINIC], *WINDOW)


def test_services_from_config_skip_disabled():
    services = permit_connector.PermitService.from_options(CONFIG.sources["PERMIT_DAILY"].options)
    paths = {s.path for s in services}
    assert "general_restaurants" in paths and "clinics" in paths
    assert "ecommerce_businesses" not in paths
    assert all(s.service_id and s.name for s in services)


def test_parse_new_api_row():
    row = {
        "MNG_NO": "3010000-101-2026-00001", "BPLC_NM": "예시식당", "BZSTAT_SE_NM": "한식",
        "SALS_STTS_CD": "01", "SALS_STTS_NM": "영업/정상", "DTL_SALS_STTS_NM": "영업",
        "LCPMT_YMD": "2026-10-02", "CLSBIZ_YMD": "", "ROAD_NM_ADDR": "서울특별시 중구 예시로 1",
        "LOTNO_ADDR": "서울특별시 중구 예시동 1", "DAT_UPDT_SE": "I",
        "CRD_INFO_X": "197000.12", "CRD_INFO_Y": "451000.34", "opnSvcId": "07_24_04_P", "opnSvcNm": "일반음식점",
    }
    record = parse_permit_row(row)
    assert record is not None
    # 전수 CSV와 같은 관리번호 키(서비스ID-관리번호)여야 월간·일간 적재가 같은 사업체로 합쳐진다(CONST-13).
    assert record.mgt_no == "07_24_04_P-3010000-101-2026-00001"
    assert record.industry_code == "07_24_04_P"
    assert record.industry_name == "일반음식점·한식"
    assert record.operating_status == "정상"
    assert record.licensed_on == date(2026, 10, 2)
    assert (record.x, record.y) == (197000.12, 451000.34)
    assert record.address == "서울특별시 중구 예시로 1"
    assert record.update_type == "I"


def test_parse_new_api_closed_row():
    row = {"MNG_NO": "M-2", "BPLC_NM": "폐업식당", "SALS_STTS_CD": "03", "SALS_STTS_NM": "폐업",
           "DTL_SALS_STTS_NM": "폐업", "CLSBIZ_YMD": "2026-10-04", "opnSvcId": "07_24_04_P", "opnSvcNm": "일반음식점"}
    record = parse_permit_row(row)
    assert record is not None and record.operating_status == "폐업"
    assert record.closed_on == date(2026, 10, 4)


@pytest.mark.parametrize("code", ["05", "06"])
def test_status_05_06_are_not_targets(code):
    assert map_operating_status(code, "", "") == "폐업"


def test_public_health_centers_are_excluded():
    keywords = CONFIG.exclusion.excluded_permit_keywords
    base = {"MNG_NO": "M", "SALS_STTS_CD": "01", "opnSvcId": "01_01_02_P", "opnSvcNm": "의원"}
    health_center = parse_permit_row({**base, "BPLC_NM": "중구보건소", "BZSTAT_SE_NM": "보건소"})
    branch_office = parse_permit_row({**base, "BPLC_NM": "예시동보건지소", "BZSTAT_SE_NM": ""})
    clinic = parse_permit_row({**base, "BPLC_NM": "보건소앞내과의원", "BZSTAT_SE_NM": "의원"})
    assert health_center and branch_office and clinic
    assert is_excluded_permit(health_center, keywords)
    assert is_excluded_permit(branch_office, keywords)
    assert not is_excluded_permit(clinic, keywords)


# ─────────────────────────── 변동분 창 (§1.12) ───────────────────────────

OPTIONS = {"overlap_days": 1, "max_lookback_days": 7}


def test_window_without_previous_snapshot():
    start, end = run_daily.permit_change_window(date(2026, 10, 8), 2, OPTIONS, None)
    assert (start, end) == (datetime(2026, 10, 5), datetime(2026, 10, 8))


def test_window_daily_run_keeps_lag_overlap():
    start, _ = run_daily.permit_change_window(date(2026, 10, 8), 2, OPTIONS, datetime(2026, 10, 7))
    assert start == datetime(2026, 10, 5)


def test_window_catches_up_after_missed_days():
    start, _ = run_daily.permit_change_window(date(2026, 10, 8), 2, OPTIONS, datetime(2026, 10, 4))
    assert start == datetime(2026, 10, 2)


def test_window_is_capped_by_max_lookback():
    start, _ = run_daily.permit_change_window(date(2026, 10, 8), 2, OPTIONS, datetime(2026, 9, 1))
    assert start == datetime(2026, 10, 1)


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"window": {"from": "20261004000000", "to": "20261007000000"}, "rows": []}, datetime(2026, 10, 7)),
        ({"change_date": "2026-10-05", "rows": []}, None),  # 구 형식 스냅샷
        ({"window": {"to": "bad"}}, None),
        (None, None),
    ],
)
def test_previous_window_to(payload, expected):
    assert run_daily.previous_window_to(payload) == expected
