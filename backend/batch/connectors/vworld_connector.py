"""공간정보 오픈플랫폼(VWorld) 주소 → 좌표 지오코더 (RULE-BRANCH-03, 지점 주소 전용).

사업체 좌표는 소스 데이터(상가정보 WGS84, 인허가 EPSG:5174)를 쓰며 이 지오코더를 쓰지 않는다.
"""

from __future__ import annotations

from typing import Any

from backend.batch.connectors.http_client import SourceFetchError, request_json, require


def geocode_address(api_key: str, url: str, address: str) -> tuple[float, float] | None:
    """도로명 → 지번 순으로 조회해 (lat, lng)를 돌려준다. 찾지 못하면 None."""
    require(api_key, "VWORLD_API_KEY")
    for address_type in ("road", "parcel"):
        payload = request_json(
            "GET",
            url,
            params={
                "service": "address",
                "request": "getcoord",
                "version": "2.0",
                "crs": "epsg:4326",
                "address": address,
                "refine": "true",
                "simple": "false",
                "format": "json",
                "type": address_type,
                "key": api_key,
            },
        )
        point = _extract_point(payload)
        if point is not None:
            return point
    return None


def _extract_point(payload: Any) -> tuple[float, float] | None:
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    status = response.get("status")
    if status == "NOT_FOUND":
        return None
    if status != "OK":
        error = response.get("error") or {}
        raise SourceFetchError(f"지오코딩 오류: {error.get('text') or status}")
    point = (response.get("result") or {}).get("point") or {}
    try:
        return float(point["y"]), float(point["x"])
    except (KeyError, TypeError, ValueError):
        return None
