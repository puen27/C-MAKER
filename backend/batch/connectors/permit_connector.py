"""행정안전부 지방행정 인허가 커넥터 (NAME-B03: 전수/변동분 2함수 분리).

- fetch_all_businesses: 전수 파일(CSV, F-2) → 원본 행. 월간 모집단 적재(REQ-16) 입력.
- fetch_daily_changes : 업종별 인허가 조회서비스(S-10~S-18) 변동분 → 원본 행. 일간 신규 개업·폐업 1차 신호(REQ-03).

신규 API 규격(api/11-api-spec.md §1, 2026-10-07 실호출 확인):
- End Point가 업종별로 나뉜다: {base}/{path}/info. 전 업종을 한 번에 받는 API는 없다.
- 변동분은 `cond[LAST_MDFCN_PNT::GTE]` / `::LT` (YYYYMMDDHHMMSS). 구 `lastModTsBgn`은 무시되고 전체가 온다.
- 페이징 `pageNo` + `numOfRows`(최대 100, 초과 요청은 조용히 100행), 응답 타입 `returnType=json`.
- 정상 resultCode는 "0"이다(구 표준 "00"도 허용).
- 응답에 업종 식별자(구 opnSvcId)가 없으므로 호출한 업종의 service_id/name을 행에 붙여 돌려준다.
좌표는 EPSG:5174 원본 그대로 반환한다 — 변환은 정규화 단계(VAL-11)의 몫이다.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.batch.connectors.http_client import FetchResult, SourceFetchError, request_json, require

_MAX_PAGES = 200
_TS_FORMAT = "%Y%m%d%H%M%S"
# 응답 행에 붙이는 업종 식별 키 — permit_parser가 구 API 키(opnSvcId/opnSvcNm)로 읽는다.
SERVICE_ID_KEY = "opnSvcId"
SERVICE_NAME_KEY = "opnSvcNm"


@dataclass(frozen=True)
class PermitService:
    """업종 1개 = End Point 1개. service_id는 전수 CSV의 개방서비스아이디와 맞춘 관리번호 접두어(CONST-13)."""

    service_id: str
    name: str
    path: str

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> list[PermitService]:
        services = []
        for item in options.get("services") or []:
            if not item.get("enabled", True):
                continue
            services.append(cls(service_id=str(item["service_id"]), name=str(item["name"]), path=str(item["path"])))
        return services


def fetch_all_businesses(file_path: Path) -> Iterator[dict[str, str]]:
    """전수 CSV를 한 행씩 원본 그대로 돌려준다(헤더는 한글 표준 컬럼명). 인코딩은 UTF-8(BOM)/CP949 자동 판별."""
    encoding = _detect_encoding(file_path)
    with file_path.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield {key.strip(): (value or "").strip() for key, value in row.items() if key}


def fetch_daily_changes(
    service_key: str,
    base_url: str,
    services: Sequence[PermitService],
    window_from: datetime,
    window_to: datetime,
    *,
    region_codes: Sequence[str] = (),
    page_size: int = 100,
    timeout: float | None = None,
    max_workers: int = 1,
) -> FetchResult:
    """[window_from, window_to) 사이 원천 수정(LAST_MDFCN_PNT)된 인허가 행을 업종 × 지자체별로 모은다.

    한 업종이라도 실패하면 전체를 실패로 본다. 일부만 저장하면 다음 실행의 변동분 창이 그 업종의 누락분을
    건너뛰기 때문이다(전체 실패 → 배치가 직전 스냅샷 폴백, 다음 실행이 창을 넓혀 다시 받는다).
    """
    require(base_url, "지방행정 인허가 API 엔드포인트(sources.PERMIT_DAILY.url)")
    require(service_key, "DATA_GO_KR_SERVICE_KEY")
    if not services:
        raise ValueError("수집할 인허가 업종(sources.PERMIT_DAILY.options.services)이 없습니다")
    if window_from >= window_to:
        raise ValueError("변동분 창의 시작이 끝보다 같거나 늦습니다")

    window = {"from": window_from.strftime(_TS_FORMAT), "to": window_to.strftime(_TS_FORMAT)}
    regions: list[str | None] = list(region_codes) or [None]
    tasks = [(service, region) for service in services for region in regions]

    def run(task: tuple[PermitService, str | None]) -> tuple[PermitService, str | None, list[dict[str, Any]], int]:
        service, region = task
        rows, total = _fetch_window(
            service_key, f"{base_url.rstrip('/')}/{service.path}/info", window, region,
            page_size=page_size, timeout=timeout,
        )
        return service, region, rows, total

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        results = list(pool.map(run, tasks))

    # 같은 사업장이 창 안에서 여러 번 수정됐거나 지자체 코드가 겹치면 최신 수정본 1건만 남긴다.
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    fetched: list[dict[str, Any]] = []
    for service, region, rows, total in results:
        fetched.append({"service_id": service.service_id, "path": service.path, "region": region,
                        "total_count": total, "rows": len(rows)})
        for row in rows:
            mng_no = str(row.get("MNG_NO") or "").strip()
            if not mng_no:
                continue
            tagged = {**row, SERVICE_ID_KEY: service.service_id, SERVICE_NAME_KEY: service.name}
            key = (service.service_id, mng_no)
            previous = latest.get(key)
            if previous is None or str(tagged.get("LAST_MDFCN_PNT") or "") >= str(previous.get("LAST_MDFCN_PNT") or ""):
                latest[key] = tagged

    ordered = [latest[key] for key in sorted(latest)]  # 정렬해 두어야 재실행 시 payload 해시가 같다
    return FetchResult(
        payload={"window": window, "rows": ordered},
        request_params={"url": base_url, "window": window, "region_codes": list(region_codes),
                        "services": [s.service_id for s in services], "page_size": page_size, "fetched": fetched},
    )


def _fetch_window(
    service_key: str,
    url: str,
    window: dict[str, str],
    region: str | None,
    *,
    page_size: int,
    timeout: float | None,
) -> tuple[list[dict[str, Any]], int]:
    base_params: dict[str, Any] = {
        "numOfRows": page_size,
        "returnType": "json",
        "cond[LAST_MDFCN_PNT::GTE]": window["from"],
        "cond[LAST_MDFCN_PNT::LT]": window["to"],
    }
    if region:
        base_params["cond[OPN_ATMY_GRP_CD::EQ]"] = region
    rows: list[dict[str, Any]] = []
    total = 0
    for page in range(1, _MAX_PAGES + 1):
        params = {**base_params, "serviceKey": service_key, "pageNo": page}
        payload = request_json("GET", url, params=params, timeout=timeout)
        page_rows, total = _extract_rows(payload)
        rows.extend(page_rows)
        # numOfRows 상한(100)보다 크게 요청해도 오류 없이 잘려 오므로, 받은 행 수가 아니라 totalCount로 끝을 판단한다.
        if not page_rows or len(rows) >= total:
            return rows, total
    raise SourceFetchError(f"변동분 페이지 수가 {_MAX_PAGES}을 넘었습니다: {url}")


def _extract_rows(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """data.go.kr 표준: {"response": {"header": {"resultCode": "0"}, "body": {"items": {"item": [...]}, "totalCount": n}}}"""
    if not isinstance(payload, dict):
        raise SourceFetchError("알 수 없는 응답 형식")
    response = payload.get("response", payload)
    if not isinstance(response, dict):
        raise SourceFetchError("알 수 없는 응답 형식")
    header = response.get("header") or {}
    code = str(header.get("resultCode", "0")).strip()
    if code == "03":  # NODATA
        return [], 0
    if code not in ("0", "00"):
        raise SourceFetchError(f"인허가 API 오류: {code} {header.get('resultMsg')}")
    body = response.get("body") or {}
    items = body.get("items") or {}
    item = items.get("item", []) if isinstance(items, dict) else items
    rows = item if isinstance(item, list) else ([item] if item else [])
    return rows, int(body.get("totalCount") or len(rows))


def _detect_encoding(file_path: Path) -> str:
    with file_path.open("rb") as file:
        head = file.read(64 * 1024)
    try:
        head.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp949"
