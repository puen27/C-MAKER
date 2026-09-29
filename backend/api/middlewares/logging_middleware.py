"""요청 단위 기본 로그 (OPS-08): 메서드, 경로, 상태 코드, 응답 시간만 남긴다(본문·토큰은 기록하지 않음)."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from backend.common.log_setup import log_fields

logger = logging.getLogger("api.access")


def register_logging_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def access_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            log_fields(logger, logging.INFO, "request", method=request.method, path=request.url.path,
                       status=status_code, elapsed_ms=round((time.monotonic() - started) * 1000, 1))
