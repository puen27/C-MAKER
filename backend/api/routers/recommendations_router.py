from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import quote

import psycopg
from fastapi import APIRouter, Depends, Query, Response

from backend.api.database import get_db
from backend.api.middlewares.auth_middleware import require_roles
from backend.api.services import recommendation_service
from backend.common.config import today_kst
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.brief import BriefResponse
from backend.common.schemas.recommendation import RecommendationItem, RecommendationSummary

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

_viewer = require_roles("RM", "BRANCH_MANAGER")
_exporter = require_roles("RM")  # docs/10-implementation-guide.md §6.1: CRM 파일 다운로드는 RM


@router.get("", response_model=list[RecommendationItem])
def list_recommendations(
    day: date | None = Query(default=None, alias="date"),
    user: CurrentUser = Depends(_viewer),
    conn: psycopg.Connection = Depends(get_db),
) -> list[RecommendationItem]:
    """오늘의 접촉 TOP 20 (UC-06)."""
    return recommendation_service.list_recommendations(conn, user, day or today_kst())


@router.get("/summary", response_model=RecommendationSummary)
def get_summary(
    day: date | None = Query(default=None, alias="date"),
    user: CurrentUser = Depends(_viewer),
    conn: psycopg.Connection = Depends(get_db),
) -> RecommendationSummary:
    """명부 상단 배너용 요약 — 어제 미태깅(UC-09), 상권사유비율(RULE-TARGET-06), 외 N건(RULE-SENSE-02)."""
    return recommendation_service.get_summary(conn, user, day or today_kst())


@router.get("/export")
def export_recommendations(
    day: date | None = Query(default=None, alias="date"),
    file_format: Literal["csv", "xlsx"] = Query(default="csv", alias="format"),
    user: CurrentUser = Depends(_exporter),
    conn: psycopg.Connection = Depends(get_db),
) -> Response:
    """CRM 등록 파일 다운로드 (UC-08)."""
    content, filename, media_type = recommendation_service.build_export(conn, user, day or today_kst(), file_format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{recommendation_id}/brief", response_model=BriefResponse)
def get_brief(
    recommendation_id: int,
    user: CurrentUser = Depends(_viewer),
    conn: psycopg.Connection = Depends(get_db),
) -> BriefResponse:
    """상담 브리프 상세 (UC-07)."""
    return recommendation_service.get_brief(conn, user, recommendation_id)
