"""커넥터 공통 HTTP 호출 헬퍼 — 외부 API 오류를 `SourceFetchError`로 통일한다(OPS-04 소스별 실패 격리)."""

from __future__ import annotations

import re
from typing import Any

import requests
from pydantic import BaseModel, Field

from backend.common.config import get_settings


class SourceFetchError(RuntimeError):
    """외부 소스 호출 실패. 배치는 이 예외를 소스 단위로 잡아 전일 스냅샷으로 폴백한다(RULE-SENSE-04)."""


class SourceNotConfiguredError(SourceFetchError):
    """인증키·엔드포인트가 설정되지 않아 호출하지 않은 경우."""


class FetchResult(BaseModel):
    """커넥터 반환값: 원본 응답과 (인증키를 제외한) 요청 파라미터."""

    payload: Any
    request_params: dict[str, Any] = Field(default_factory=dict)


# data.go.kr 게이트웨이는 인증 오류 시 JSON 요청에도 XML을 돌려준다.
_DATA_GO_KR_ERROR = re.compile(r"<returnAuthMsg>([^<]+)</returnAuthMsg>")


def require(value: str, what: str) -> str:
    if not value:
        raise SourceNotConfiguredError(f"{what}이(가) 설정되지 않았습니다")
    return value


def request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    timeout: float | None = None,
) -> Any:
    try:
        response = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            timeout=timeout or get_settings().external_http_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise SourceFetchError(f"요청 실패: {type(exc).__name__}") from exc

    text = response.text
    if response.status_code >= 400:
        raise SourceFetchError(f"HTTP {response.status_code}: {text[:200]}")
    try:
        return response.json()
    except ValueError as exc:
        match = _DATA_GO_KR_ERROR.search(text)
        message = match.group(1) if match else text[:200]
        raise SourceFetchError(f"JSON이 아닌 응답: {message}") from exc
