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
    seen_ids: set[str] = set()
    expected_total: int | None = None

    for page in range(1, _MAX_PAGES + 1):
        payload = request_json(
            "GET",
            url,
            params={**base_params, "pageNo": page, "serviceKey": service_key},
        )
        page_items, page_total = _extract_items(payload)
        if expected_total is None:
            expected_total = page_total
        elif page_total != expected_total:
            raise SourceFetchError(
                f"상가정보 totalCount가 페이지 사이에 변경되었습니다: "
                f"first={expected_total}, page={page}, current={page_total}"
            )

        for item in page_items:
            store_id = str(item.get("bizesId") or "").strip()
            if store_id:
                if store_id in seen_ids:
                    raise SourceFetchError(f"상가정보 bizesId가 중복되었습니다: page={page}, bizesId={store_id}")
                seen_ids.add(store_id)
        items.extend(page_items)

        assert expected_total is not None
        if len(seen_ids) > expected_total:
            raise SourceFetchError(
                f"상가정보 고유 bizesId 수가 totalCount를 초과했습니다: "
                f"unique={len(seen_ids)}, total={expected_total}"
            )
        if len(seen_ids) == expected_total:
            return FetchResult(
                payload={
                    "items": items,
                    "complete": True,
                    "unique_count": len(seen_ids),
                    "total_count": expected_total,
                    "pages_fetched": page,
                },
                request_params={**base_params, "url": url},
            )
        if not page_items:
            raise SourceFetchError(
                f"상가정보가 totalCount 도달 전에 빈 페이지를 반환했습니다: "
                f"page={page}, unique={len(seen_ids)}, total={expected_total}"
            )

    raise SourceFetchError(
        f"상가정보 페이지 상한({_MAX_PAGES}) 내에 전수를 수집하지 못했습니다: "
        f"unique={len(seen_ids)}, total={expected_total}"
    )


def _extract_items(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise SourceFetchError("알 수 없는 응답 형식")
    header = payload.get("header") or (payload.get("response") or {}).get("header") or {}
    body = payload.get("body") or (payload.get("response") or {}).get("body") or {}
    code = str(header.get("resultCode", "00"))
    if code == "03":
        raise SourceFetchError(
            f"상가정보 API가 NO_DATA(resultCode=03)를 반환했습니다: {header.get('resultMsg')}"
        )
    if code != "00":
        raise SourceFetchError(f"상가정보 API 오류: {header.get('resultMsg')}")
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise SourceFetchError("상가정보 items 형식이 올바르지 않습니다")

    raw_total = body.get("totalCount")
    try:
        total = len(items) if raw_total in (None, "") else int(raw_total)
    except (TypeError, ValueError) as exc:
        raise SourceFetchError("상가정보 totalCount 형식이 올바르지 않습니다") from exc
    if total < 0:
        raise SourceFetchError("상가정보 totalCount는 음수일 수 없습니다")
    return items, total
