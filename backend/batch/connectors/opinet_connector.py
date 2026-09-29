"""오피넷 유가정보 커넥터 — 시도별 평균 가격(일). 시도 단위라 지점 소재 시도로 매핑해 쓴다."""

from __future__ import annotations

from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require


def fetch_sido_average_prices(api_key: str, url: str, *, prodcd: str) -> FetchResult:
    require(api_key, "OPINET_API_KEY")
    payload = request_json("GET", url, params={"out": "json", "code": api_key, "prodcd": prodcd})
    oil = _extract_oil(payload)
    return FetchResult(payload={"oil": oil, "prodcd": prodcd}, request_params={"url": url, "prodcd": prodcd})


def _extract_oil(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or "RESULT" not in payload:
        raise SourceFetchError("알 수 없는 응답 형식")
    oil = payload["RESULT"].get("OIL", [])
    return oil if isinstance(oil, list) else [oil]
