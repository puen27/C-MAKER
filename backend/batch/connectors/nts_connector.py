"""국세청 사업자등록정보 상태조회 커넥터 (S-8, REQ-02 보완 검증).

⚠ 사업자번호가 확보된 보유 명부 검증 전용이다. 신규 개업 탐지용으로 쓰지 않는다(CLAUDE.md §7).
호출 한도: 1회 100건 · 1일 100만 건 — 1회 호출에 100건을 넘기지 않는다.
"""

from __future__ import annotations

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require

MAX_NUMBERS_PER_CALL = 100


def fetch_business_status(service_key: str, url: str, biz_reg_nos: list[str]) -> FetchResult:
    require(service_key, "DATA_GO_KR_SERVICE_KEY")
    if not biz_reg_nos:
        return FetchResult(payload={"data": []}, request_params={"count": 0})
    if len(biz_reg_nos) > MAX_NUMBERS_PER_CALL:
        raise ValueError(f"국세청 상태조회는 1회 {MAX_NUMBERS_PER_CALL}건까지만 요청할 수 있습니다")

    payload = request_json(
        "POST",
        url,
        params={"serviceKey": service_key, "returnType": "JSON"},
        json_body={"b_no": biz_reg_nos},
    )
    if not isinstance(payload, dict) or payload.get("status_code") not in (None, "OK"):
        raise SourceFetchError(f"국세청 API 오류: {payload.get('status_code') if isinstance(payload, dict) else payload}")
    return FetchResult(payload=payload, request_params={"url": url, "count": len(biz_reg_nos)})
