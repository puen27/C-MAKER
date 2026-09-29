"""인증 API 스키마 (docs/10-implementation-guide.md §6.3 로그인)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.common.schemas.recommendation import ApiModel

UserRole = Literal["RM", "BRANCH_MANAGER", "HQ_MARKETING", "HQ_COMPLIANCE"]


class LoginRequest(ApiModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class AuthUser(ApiModel):
    id: int
    name: str
    role: UserRole
    branch_id: int | None
    branch_name: str | None
    branch_code: str | None
    session_timeout_minutes: int
    session_extendable: bool


class LoginResponse(ApiModel):
    token: str
    expires_at: str
    user: AuthUser


class CurrentUser(ApiModel):
    """JWT에서 복원한 요청 주체. 권한 검증(VAL-08)에 쓴다."""

    id: int
    role: UserRole
    branch_id: int | None
