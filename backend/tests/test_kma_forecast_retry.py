"""기상청 예보 커넥터 재시도와 수집 실패 로그 문구(인증키 마스킹) 검증."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.batch import run_daily
from backend.batch.connectors import kma_forecast_connector as k
from backend.batch.connectors.http_client import SourceFetchError, SourceNotConfiguredError

OK = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                   "body": {"items": {"item": [{"category": "TMN", "fcstDate": "20261016",
                                                 "fcstTime": "0600", "fcstValue": "8"}]}}}}
OPTIONS = {"short_path": "s", "mid_ta_path": "t", "mid_land_path": "l", "retry_backoff_seconds": 0}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(k.time, "sleep", lambda _s: None)


def _scripted(monkeypatch, responses):
    calls: list[str] = []

    def fake(method, url, *, params=None, **_kw):
        calls.append(url)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(k, "request_json", fake)
    return calls


def test_short_forecast_recovers_after_transient_error(monkeypatch):
    calls = _scripted(monkeypatch, [SourceFetchError("JSON이 아닌 응답: SERVICE ERROR"), OK])

    result = k.fetch_forecasts("key", "https://x", options=OPTIONS, grids=[(58, 125)],
                               mid_ta_regions=[], mid_land_regions=[], target_date=date(2026, 10, 15))

    assert len(calls) == 2
    assert result.payload["short"]["grids"]["58,125"][0]["category"] == "TMN"


def test_error_code_in_body_is_retried(monkeypatch):
    bad = {"response": {"header": {"resultCode": "99", "resultMsg": "TEMP"}}}
    calls = _scripted(monkeypatch, [bad, OK])

    assert k._fetch_items("https://x/s", {}, "key", OPTIONS) == OK["response"]["body"]["items"]["item"]
    assert len(calls) == 2


def test_gives_up_after_configured_retries(monkeypatch):
    calls = _scripted(monkeypatch, [SourceFetchError("e1"), SourceFetchError("e2"), SourceFetchError("e3")])

    with pytest.raises(SourceFetchError, match="e3"):
        k._fetch_items("https://x/s", {}, "key", {**OPTIONS, "retries": 2})
    assert len(calls) == 3


def test_not_configured_is_not_retried(monkeypatch):
    calls = _scripted(monkeypatch, [SourceNotConfiguredError("no key"), OK])

    with pytest.raises(SourceNotConfiguredError):
        k._fetch_items("https://x/s", {}, "key", OPTIONS)
    assert len(calls) == 1


def test_no_data_is_not_an_error(monkeypatch):
    no_data = {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}}
    calls = _scripted(monkeypatch, [no_data])

    assert k._fetch_items("https://x/s", {}, "key", OPTIONS) == []
    assert len(calls) == 1


def test_log_detail_masks_service_key_and_skips_foreign_exceptions(monkeypatch):
    secret = "abc+def/ghi=="
    monkeypatch.setattr(run_daily, "get_settings", lambda: SimpleNamespace(data_go_kr_service_key=secret))

    detail = run_daily._log_error_detail(SourceFetchError(f"HTTP 500: key={secret} enc=abc%2Bdef%2Fghi%3D%3D"))
    assert detail is not None
    assert secret not in detail and "abc%2Bdef" not in detail
    assert detail.startswith("HTTP 500")
    assert run_daily._log_error_detail(RuntimeError(f"api-key={secret}")) is None
    assert len(run_daily._log_error_detail(SourceFetchError("x" * 500)) or "") == 200
