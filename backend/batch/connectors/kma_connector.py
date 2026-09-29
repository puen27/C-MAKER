"""기상청 기상특보 조회서비스 커넥터 (S-2).

특보 발효/해제만 신호가 된다. 단기·중기 예보(S-4/S-5)는 이벤트 승격 대상이 아니므로 수집하지 않는다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require


def fetch_weather_warnings(
    service_key: str,
    url: str,
    *,
    station_ids: list[int],
    target_date: date,
) -> FetchResult:
    """발표 관서(stnId)별로 전일~당일 발표된 특보 목록을 모은다."""
    require(service_key, "DATA_GO_KR_SERVICE_KEY")
    from_ymd = (target_date - timedelta(days=1)).strftime("%Y%m%d")
    to_ymd = target_date.strftime("%Y%m%d")

    stations: dict[str, list[dict[str, Any]]] = {}
    for station_id in sorted(set(station_ids)):
        params = {
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
            "stnId": station_id,
            "fromTmFc": from_ymd,
            "toTmFc": to_ymd,
        }
        payload = request_json("GET", url, params={**params, "serviceKey": service_key})
        stations[str(station_id)] = _extract_items(payload)

    return FetchResult(
        payload={"target_date": target_date.isoformat(), "stations": stations},
        request_params={"url": url, "station_ids": sorted(set(station_ids)), "from": from_ymd, "to": to_ymd},
    )


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    header = response.get("header") or {}
    code = str(header.get("resultCode", ""))
    if code == "03":  # NODATA_ERROR — 특보 없음
        return []
    if code != "00":
        raise SourceFetchError(f"기상특보 API 오류: {header.get('resultMsg')}")
    items = ((response.get("body") or {}).get("items") or {}).get("item", [])
    return items if isinstance(items, list) else [items]
