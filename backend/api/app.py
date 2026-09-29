"""C-MAKER API 서버 (FastAPI).

실행: python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
Nginx가 /api/* 를 이 서버로 프록시한다(docs/10-implementation-guide.md §2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.middlewares.error_middleware import register_error_handlers
from backend.api.middlewares.logging_middleware import register_logging_middleware
from backend.api.routers import (
    auth_router,
    batch_router,
    recommendations_router,
    tags_router,
    thresholds_router,
)
from backend.api.security import get_jwt_secret
from backend.common.config import get_pipeline_config, get_settings
from backend.common.db.pool import close_pool, open_pool
from backend.common.log_setup import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging("api")
    get_jwt_secret()  # 운영에서 JWT_SECRET이 없으면 기동을 거부한다
    get_pipeline_config()
    open_pool()  # OPS-02: 프로세스 시작 시 1회 생성
    try:
        yield
    finally:
        close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="C-MAKER API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.is_dev else None,
    )
    # OPS-07: 프런트엔드 배포 origin만 허용한다(와일드카드 금지).
    origins = [origin.strip() for origin in settings.frontend_origin.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    register_logging_middleware(app)
    register_error_handlers(app)

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (auth_router, recommendations_router, tags_router, thresholds_router, batch_router):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
