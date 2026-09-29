"""한국은행 ECOS 커넥터 — 원/달러 매매기준율(일). BSI 등 월 단위 지표는 일간 이벤트 대상이 아니다."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require


def fetch_exchange_rates(
    api_key: str,
    url: str,
    *,
    stat_code: str,
    item_code: str,
    cycle: str,
    start: date,
    end: date,
) -> FetchResult:
    require(api_key, "ECOS_API_KEY")
    start_ymd, end_ymd = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    # ECOS는 인증키가 URL 경로에 들어간다 — request_params에는 키를 남기지 않는다.
    request_url = f"{url.rstrip('/')}/{api_key}/json/kr/1/100/{stat_code}/{cycle}/{start_ymd}/{end_ymd}/{item_code}"
    payload = request_json("GET", request_url)
    rows = _extract_rows(payload)
    return FetchResult(
        payload={"rows": rows},
        request_params={"url": url, "stat_code": stat_code, "item_code": item_code, "cycle": cycle,
                        "start": start_ymd, "end": end_ymd},
    )


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise SourceFetchError("알 수 없는 응답 형식")
    if "RESULT" in payload:
        result = payload["RESULT"]
        if result.get("CODE") == "INFO-200":  # 해당 데이터 없음
            return []
        raise SourceFetchError(f"ECOS 오류: {result.get('CODE')} {result.get('MESSAGE')}")
    rows = (payload.get("StatisticSearch") or {}).get("row", [])
    return rows if isinstance(rows, list) else [rows]
