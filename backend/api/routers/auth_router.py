from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from backend.api.database import get_db
from backend.api.middlewares.auth_middleware import get_current_user
from backend.api.services import auth_service
from backend.common.schemas.auth import CurrentUser, LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, conn: psycopg.Connection = Depends(get_db)) -> LoginResponse:
    return auth_service.login(conn, request)


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    user: CurrentUser = Depends(get_current_user), conn: psycopg.Connection = Depends(get_db)
) -> LoginResponse:
    """세션 연장(상단 유틸리티 바 '연장' 버튼)."""
    return auth_service.refresh(conn, user)
