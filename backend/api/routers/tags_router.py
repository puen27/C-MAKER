from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from backend.api.database import get_db
from backend.api.middlewares.auth_middleware import require_roles
from backend.api.services import tag_service
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.recommendation import TagRequest, TagResponse

router = APIRouter(prefix="/recommendations", tags=["tags"])

_tagger = require_roles("RM")


@router.post("/{recommendation_id}/tag", response_model=TagResponse)
def save_tag(
    recommendation_id: int,
    request: TagRequest,
    user: CurrentUser = Depends(_tagger),
    conn: psycopg.Connection = Depends(get_db),
) -> TagResponse:
    """1클릭 태깅 저장 (UC-09, VAL-06)."""
    return tag_service.save_tag(conn, user, recommendation_id, request)


@router.delete("/{recommendation_id}/tag", response_model=TagResponse)
def remove_tag(
    recommendation_id: int,
    user: CurrentUser = Depends(_tagger),
    conn: psycopg.Connection = Depends(get_db),
) -> TagResponse:
    """태깅 되돌리기 (UC-09 '저장 직후 되돌리기 가능')."""
    return tag_service.remove_tag(conn, user, recommendation_id)
