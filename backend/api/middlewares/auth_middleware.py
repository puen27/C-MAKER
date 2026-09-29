"""인증/인가 공통 처리 (OPS-03): JWT 검증 + 역할 제한. 소속 지점 기반 데이터 접근 제어는 서비스 레이어가 한다."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.api.database import get_db
from backend.api.middlewares.error_middleware import ForbiddenError, UnauthorizedError
from backend.api.security import decode_access_token
from backend.api.services import auth_service
from backend.common.schemas.auth import CurrentUser, UserRole

_bearer = HTTPBearer(auto_error=False)


def _token_claims(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict[str, Any]:
    """토큰 검증을 DB 커넥션 획득보다 먼저 한다 — 미인증 요청이 커넥션 풀을 쓰지 않게 한다."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise UnauthorizedError("로그인이 필요합니다.")
    return decode_access_token(credentials.credentials)


def get_current_user(
    claims: dict[str, Any] = Depends(_token_claims),
    conn: psycopg.Connection = Depends(get_db),
) -> CurrentUser:
    return auth_service.resolve_current_user(conn, claims)


def require_roles(*roles: UserRole) -> Callable[..., CurrentUser]:
    allowed = set(roles)

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise ForbiddenError("이 기능에 대한 권한이 없습니다.")
        return user

    return dependency
