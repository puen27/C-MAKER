"""JWT 발급/검증 (PyJWT, HS256)."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt

from backend.api.middlewares.error_middleware import UnauthorizedError
from backend.common.config import KST, get_settings

logger = logging.getLogger("api.security")
_MIN_SECRET_LENGTH = 32


@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """JWT_SECRET이 없으면 운영에서는 기동을 거부한다. 개발(APP_ENV=dev)에서만 임시 키를 만든다."""
    settings = get_settings()
    secret = settings.jwt_secret
    if secret and len(secret) >= _MIN_SECRET_LENGTH:
        return secret
    if settings.is_dev:
        logger.warning("JWT_SECRET 미설정(또는 32자 미만) — 개발용 임시 키를 사용합니다. 재기동 시 토큰이 무효화됩니다.")
        return secrets.token_urlsafe(48)
    raise RuntimeError("JWT_SECRET이 설정되지 않았거나 32자 미만입니다(.env 확인)")


def session_minutes(session_timeout_minutes: int) -> int:
    """토큰 수명 = 계정 세션 정책(비활동 자동 로그아웃)과 JWT_EXPIRE_MINUTES 중 짧은 값."""
    return max(1, min(session_timeout_minutes, get_settings().jwt_expire_minutes))


def create_access_token(*, user_id: int, role: str, branch_id: int | None, minutes: int) -> tuple[str, datetime]:
    now = datetime.now(KST)
    expires_at = now + timedelta(minutes=minutes)
    claims = {
        "sub": str(user_id),
        "role": role,
        "branch_id": branch_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, get_jwt_secret(), algorithm=get_settings().jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[get_settings().jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("세션이 만료되었습니다. 다시 로그인해주세요.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("인증 정보가 올바르지 않습니다.", code="INVALID_TOKEN") from exc
