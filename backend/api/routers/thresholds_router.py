from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from backend.api.database import get_db
from backend.api.middlewares.auth_middleware import require_roles
from backend.api.services import threshold_service
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.threshold import ThresholdHistoryItem, ThresholdUpdateRequest, ThresholdView

router = APIRouter(prefix="/thresholds", tags=["thresholds"])

_hq_marketing = require_roles("HQ_MARKETING")


@router.get("", response_model=list[ThresholdView])
def list_thresholds(
    _user: CurrentUser = Depends(_hq_marketing), conn: psycopg.Connection = Depends(get_db)
) -> list[ThresholdView]:
    return threshold_service.list_thresholds(conn)


@router.put("/{threshold_id}", response_model=ThresholdView)
def update_threshold(
    threshold_id: int,
    request: ThresholdUpdateRequest,
    user: CurrentUser = Depends(_hq_marketing),
    conn: psycopg.Connection = Depends(get_db),
) -> ThresholdView:
    return threshold_service.update_threshold(conn, user, threshold_id, request)


@router.get("/{threshold_id}/history", response_model=list[ThresholdHistoryItem])
def threshold_history(
    threshold_id: int,
    _user: CurrentUser = Depends(_hq_marketing),
    conn: psycopg.Connection = Depends(get_db),
) -> list[ThresholdHistoryItem]:
    return threshold_service.threshold_history(conn, threshold_id)
