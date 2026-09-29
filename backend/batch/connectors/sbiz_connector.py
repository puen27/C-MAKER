"""소상공인시장진흥공단 상가(상권)정보 커넥터 (S-1).

반경 내 영업 중 상가업소 전수를 WGS84 좌표로 제공한다 → 월간 모집단 적재(REQ-16) 입력.
분기 점포 증감 신호(REQ-04)는 Phase 2이며 여기서 만들지 않는다.
"""

from __future__ import annotations

from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require

_MAX_PAGES = 100


def fetch_stores_in_radius(
    service_key: str,
    url: str,
    *,
    lat: float,
    lng: float,
    radius_m: int,
    page_size: int = 1000,
) -> FetchResult:
    require(service_key, "DATA_GO_KR_SERVICE_KEY")
    require(url, "상가(상권)정보 API 엔드포인트")

    base_params: dict[str, Any] = {
        "radius": radius_m,
        "cx": round(lng, 7),
        "cy": round(lat, 7),
        "numOfRows": page_size,
        "type": "json",
    }
    items: list[dict[str, Any]] = []
    total = 0
    for page in range(1, _MAX_PAGES + 1):
        payload = request_json("GET", url, params={**base_params, "pageNo": page, "serviceKey": service_key})
        page_items, total = _extract_items(payload)
        items.extend(page_items)
        if not page_items or len(items) >= total:
            break
    return FetchResult(
        payload={"items": items, "total_count": total},
        request_params={**base_params, "url": url},
    )


def _extract_items(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise SourceFetchError("알 수 없는 응답 형식")
    header = payload.get("header") or (payload.get("response") or {}).get("header") or {}
    body = payload.get("body") or (payload.get("response") or {}).get("body") or {}
    code = str(header.get("resultCode", "00"))
    if code == "03":
        return [], 0
    if code != "00":
        raise SourceFetchError(f"상가정보 API 오류: {header.get('resultMsg')}")
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return list(items), int(body.get("totalCount") or len(items))
