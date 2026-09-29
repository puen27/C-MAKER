"""행정안전부 지방행정 인허가 커넥터 (NAME-B03: 전수/변동분 2함수 분리).

- fetch_all_businesses: 전수 파일(CSV, F-2) → 원본 행. 월간 모집단 적재(REQ-16) 입력.
- fetch_daily_changes : 변동분 API(N-1) → 원본 행. 일간 신규 개업·폐업 1차 신호(REQ-03) 입력.

⚠ 변동분 API는 아직 활용신청 전(N-1)이다. 엔드포인트는 pipeline.toml `sources.PERMIT_DAILY.url`로
주입하며, 응답은 구 localdata 표준(result.body.rows[].row[]) 과 data.go.kr 표준(response.body.items.item[])
두 형태를 모두 받아들인다. 실제 스펙 확정 후 파싱 필드를 재확인해야 한다.
좌표는 EPSG:5174 원본 그대로 반환한다 — 변환은 정규화 단계(VAL-11)의 몫이다.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require

_MAX_PAGES = 200


def fetch_all_businesses(file_path: Path) -> Iterator[dict[str, str]]:
    """전수 CSV를 한 행씩 원본 그대로 돌려준다(헤더는 한글 표준 컬럼명). 인코딩은 UTF-8(BOM)/CP949 자동 판별."""
    encoding = _detect_encoding(file_path)
    with file_path.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield {key.strip(): (value or "").strip() for key, value in row.items() if key}


def fetch_daily_changes(
    service_key: str,
    url: str,
    change_date: date,
    *,
    page_size: int = 500,
) -> FetchResult:
    """`change_date` 하루 동안 변경된 인허가 행 전체를 페이지 단위로 모아 돌려준다."""
    require(url, "지방행정 인허가 변동분 API 엔드포인트(sources.PERMIT_DAILY.url)")
    require(service_key, "DATA_GO_KR_SERVICE_KEY")

    ymd = change_date.strftime("%Y%m%d")
    base_params: dict[str, Any] = {
        "lastModTsBgn": ymd,
        "lastModTsEnd": ymd,
        "pageSize": page_size,
        "numOfRows": page_size,
        "resultType": "json",
        "type": "json",
    }
    rows: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        params = {**base_params, "serviceKey": service_key, "pageIndex": page, "pageNo": page}
        payload = request_json("GET", url, params=params)
        page_rows, total = _extract_rows(payload)
        rows.extend(page_rows)
        if not page_rows or len(rows) >= total:
            break
    else:
        raise SourceFetchError(f"변동분 페이지 수가 {_MAX_PAGES}을 넘었습니다")

    return FetchResult(
        payload={"change_date": change_date.isoformat(), "rows": rows},
        request_params={**base_params, "url": url},
    )


def _extract_rows(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        raise SourceFetchError("알 수 없는 응답 형식")

    # 구 localdata 표준: {"result": {"header": {"paging": {"totalCount": n}}, "body": {"rows": [{"row": [...]}]}}}
    result = payload.get("result")
    if isinstance(result, dict):
        header = result.get("header") or {}
        process = header.get("process") or {}
        if process.get("code") not in (None, "00"):
            raise SourceFetchError(f"인허가 API 오류: {process.get('message')}")
        body = result.get("body") or {}
        rows_block = body.get("rows") or []
        rows: list[dict[str, Any]] = []
        for block in rows_block:
            value = block.get("row") if isinstance(block, dict) else None
            if isinstance(value, list):
                rows.extend(value)
            elif isinstance(value, dict):
                rows.append(value)
        total = int((header.get("paging") or {}).get("totalCount") or len(rows))
        return rows, total

    # data.go.kr 표준: {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [...]}, "totalCount": n}}}
    response = payload.get("response", payload)
    header = response.get("header") or {}
    code = str(header.get("resultCode", "00"))
    if code == "03":  # NODATA
        return [], 0
    if code != "00":
        raise SourceFetchError(f"인허가 API 오류: {header.get('resultMsg')}")
    body = response.get("body") or {}
    items = body.get("items") or {}
    item = items.get("item", []) if isinstance(items, dict) else items
    rows = item if isinstance(item, list) else [item]
    return rows, int(body.get("totalCount") or len(rows))


def _detect_encoding(file_path: Path) -> str:
    with file_path.open("rb") as file:
        head = file.read(64 * 1024)
    try:
        head.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp949"
