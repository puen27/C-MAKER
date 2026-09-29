"""로그인·세션 연장·요청 주체 복원.

⚠ 비밀번호는 결정 사항(docs/db-schema-decisions-review.md)에 따라 평문으로 저장·비교한다.
타이밍 공격을 줄이기 위해 hmac.compare_digest로 비교하고, 실패 사유(아이디 없음/비밀번호 불일치)를
구분하지 않는다. 운영 전환 전 해싱 적용 여부를 보안팀과 재검토해야 한다.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

import psycopg

from backend.api.middlewares.error_middleware import ForbiddenError, UnauthorizedError
from backend.api.repositories import user_repository
from backend.api.security import create_access_token, session_minutes
from backend.common.schemas.auth import AuthUser, CurrentUser, LoginRequest, LoginResponse

logger = logging.getLogger("api.auth")
_LOGIN_FAILED = "아이디 또는 비밀번호가 올바르지 않습니다."


def _to_auth_user(row: dict[str, Any]) -> AuthUser:
    return AuthUser(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        branch_id=row["branch_id"],
        branch_name=row["branch_name"],
        branch_code=row["branch_code"],
        session_timeout_minutes=session_minutes(row["session_timeout_minutes"]),
        session_extendable=row["session_extendable"],
    )


def _issue(row: dict[str, Any]) -> LoginResponse:
    token, expires_at = create_access_token(
        user_id=row["id"], role=row["role"], branch_id=row["branch_id"],
        minutes=session_minutes(row["session_timeout_minutes"]),
    )
    return LoginResponse(token=token, expires_at=expires_at.isoformat(), user=_to_auth_user(row))


def login(conn: psycopg.Connection, request: LoginRequest) -> LoginResponse:
    row = user_repository.find_by_username(conn, request.username.strip())
    stored = row["password"] if row else ""
    matched = hmac.compare_digest(stored.encode("utf-8"), request.password.encode("utf-8"))
    if row is None or not matched or not row["is_active"]:
        logger.warning("로그인 실패", extra={"fields": {"username_length": len(request.username)}})
        raise UnauthorizedError(_LOGIN_FAILED, code="LOGIN_FAILED")
    return _issue(row)


def refresh(conn: psycopg.Connection, current: CurrentUser) -> LoginResponse:
    """세션 연장 — 계정 정책상 연장 가능한 경우에만 새 토큰을 발급한다."""
    row = user_repository.find_by_id(conn, current.id)
    if row is None or not row["is_active"]:
        raise UnauthorizedError("계정을 사용할 수 없습니다.")
    if not row["session_extendable"]:
        raise ForbiddenError("이 계정은 세션 연장이 허용되지 않습니다.", code="SESSION_NOT_EXTENDABLE")
    return _issue(row)


def resolve_current_user(conn: psycopg.Connection, claims: dict[str, Any]) -> CurrentUser:
    """토큰의 역할·소속이 DB와 다르면(권한 변경·비활성화) 토큰을 무효로 본다."""
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedError("인증 정보가 올바르지 않습니다.", code="INVALID_TOKEN") from exc
    row = user_repository.find_by_id(conn, user_id)
    if row is None or not row["is_active"] or row["role"] != claims.get("role") or row["branch_id"] != claims.get(
        "branch_id"
    ):
        raise UnauthorizedError("권한 정보가 변경되었습니다. 다시 로그인해주세요.", code="INVALID_TOKEN")
    return CurrentUser(id=row["id"], role=row["role"], branch_id=row["branch_id"])
