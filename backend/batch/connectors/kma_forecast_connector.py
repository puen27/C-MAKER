"""기상청 단기예보·중기예보 커넥터 (S-4/S-5) + 초단기실황 (관측 누적용).

예보는 '강한 예보만 이벤트'로 쓴다(docs/2-prd.md 4장): 기온 급변·계절 전환·첫 영하·첫 폭염은 이벤트 후보,
비·눈 예보는 브리프 '날씨 참고'로만 쓴다. 판정은 normalizers/forecast_normalizer.py가 한다.

- 단기예보(getVilageFcst): 지점 격자(nx, ny)별. 기준일 02시 발표분을 쓴다 — 05시 발표에는 당일 최저기온이 없다.
- 중기기온(getMidTa)·중기육상(getMidLandFcst): 시·도 대표 지역코드별. 06:00 배치 시점에는 당일 06시 발표가
  아직 없을 수 있어 전날 18시 발표분을 쓴다. 키의 숫자(taMin5 등)는 발표일 기준 N일 뒤다.
- 초단기실황(getUltraSrtNcst): 신호로 쓰지 않고 스냅샷만 쌓는다(ASOS 미승인 대안, 관측 근거 축적).

인증키는 request_params에 남기지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require

# 단기예보에서 판정에 쓰는 항목만 보관한다(스냅샷 크기 절감).
SHORT_CATEGORIES = frozenset({"TMN", "TMX", "POP", "PTY", "SNO"})


def _items(payload: Any) -> list[dict[str, Any]]:
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    header = response.get("header") or {}
    code = str(header.get("resultCode", ""))
    if code == "03":  # NO_DATA
        return []
    if code != "00":
        raise SourceFetchError(f"기상청 예보 API 오류: {header.get('resultCode')} {header.get('resultMsg')}")
    items = ((response.get("body") or {}).get("items") or {}).get("item", [])
    return items if isinstance(items, list) else [items]


def grid_key(nx: int, ny: int) -> str:
    return f"{nx},{ny}"


def mid_issue_time(target_date: date) -> str:
    """전날 18시 발표(YYYYMMDDHHMM)."""
    return (target_date - timedelta(days=1)).strftime("%Y%m%d") + "1800"


def fetch_forecasts(
    service_key: str,
    base_url: str,
    *,
    options: dict[str, Any],
    grids: list[tuple[int, int]],
    mid_ta_regions: list[str],
    mid_land_regions: list[str],
    target_date: date,
) -> FetchResult:
    require(service_key, "DATA_GO_KR_SERVICE_KEY")
    base = base_url.rstrip("/")
    base_date = target_date.strftime("%Y%m%d")
    base_time = str(options.get("short_base_time", "0200"))

    short: dict[str, list[dict[str, Any]]] = {}
    for nx, ny in sorted(set(grids)):
        params = {
            "pageNo": 1,
            "numOfRows": int(options.get("short_num_rows", 1500)),
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        }
        payload = request_json("GET", f"{base}/{options['short_path']}", params={**params, "serviceKey": service_key})
        short[grid_key(nx, ny)] = [
            {key: item.get(key) for key in ("category", "fcstDate", "fcstTime", "fcstValue")}
            for item in _items(payload)
            if item.get("category") in SHORT_CATEGORIES
        ]
    if not any(short.values()):
        raise SourceFetchError("단기예보 응답이 비어 있습니다")

    # 중기예보는 실패해도 단기예보 판정은 계속한다(계절 전환·5일 이후 첫 영하/폭염만 빠진다).
    tm_fc = mid_issue_time(target_date)
    mid_ta: dict[str, dict[str, Any]] = {}
    mid_land: dict[str, dict[str, Any]] = {}
    mid_error: str | None = None
    try:
        for reg_id in sorted(set(mid_ta_regions)):
            params = {"pageNo": 1, "numOfRows": 10, "dataType": "JSON", "regId": reg_id, "tmFc": tm_fc}
            items = _items(request_json("GET", f"{base}/{options['mid_ta_path']}",
                                        params={**params, "serviceKey": service_key}))
            if items:
                mid_ta[reg_id] = items[0]
        for reg_id in sorted(set(mid_land_regions)):
            params = {"pageNo": 1, "numOfRows": 10, "dataType": "JSON", "regId": reg_id, "tmFc": tm_fc}
            items = _items(request_json("GET", f"{base}/{options['mid_land_path']}",
                                        params={**params, "serviceKey": service_key}))
            if items:
                mid_land[reg_id] = items[0]
    except SourceFetchError as exc:
        mid_error = type(exc).__name__

    return FetchResult(
        payload={
            "target_date": target_date.isoformat(),
            "short": {"base_date": base_date, "base_time": base_time, "grids": short},
            "mid": {"tm_fc": tm_fc, "ta": mid_ta, "land": mid_land, "error": mid_error},
        },
        request_params={
            "url": base,
            "grids": [grid_key(nx, ny) for nx, ny in sorted(set(grids))],
            "short_base": f"{base_date}{base_time}",
            "mid_tm_fc": tm_fc,
            "mid_ta_regions": sorted(set(mid_ta_regions)),
            "mid_land_regions": sorted(set(mid_land_regions)),
        },
    )


def nowcast_base(now: datetime) -> tuple[str, str]:
    """초단기실황은 매시 정각 관측이 약 40분 뒤 제공된다 → 1시간 전 정각을 쓴다."""
    base = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return base.strftime("%Y%m%d"), base.strftime("%H00")


def fetch_nowcast(
    service_key: str,
    base_url: str,
    *,
    path: str,
    grids: list[tuple[int, int]],
    now: datetime,
) -> FetchResult:
    require(service_key, "DATA_GO_KR_SERVICE_KEY")
    base_date, base_time = nowcast_base(now)
    observed: dict[str, dict[str, Any]] = {}
    for nx, ny in sorted(set(grids)):
        params = {"pageNo": 1, "numOfRows": 20, "dataType": "JSON", "base_date": base_date,
                  "base_time": base_time, "nx": nx, "ny": ny}
        items = _items(request_json("GET", f"{base_url.rstrip('/')}/{path}", params={**params, "serviceKey": service_key}))
        observed[grid_key(nx, ny)] = {str(item.get("category")): item.get("obsrValue") for item in items}
    return FetchResult(
        payload={"base_date": base_date, "base_time": base_time, "grids": observed},
        request_params={"url": base_url, "grids": sorted(observed), "base": f"{base_date}{base_time}"},
    )
