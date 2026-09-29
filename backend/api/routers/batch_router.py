from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from backend.api.database import get_db
from backend.api.middlewares.auth_middleware import get_current_user, require_roles
from backend.api.services import batch_service
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.batch_run import BatchStatusResponse, BatchTriggerResponse, DataFreshnessResponse

router = APIRouter(tags=["batch"])

_trigger_roles = require_roles("BRANCH_MANAGER", "HQ_MARKETING")


@router.post("/batch/trigger", response_model=BatchTriggerResponse)
def trigger_batch(
    user: CurrentUser = Depends(_trigger_roles), conn: psycopg.Connection = Depends(get_db)
) -> BatchTriggerResponse:
    """일간 배치 수동 재실행 (UC-18, RULE-SENSE-06, VAL-12)."""
    return batch_service.trigger(conn, user)


@router.get("/batch/status", response_model=BatchStatusResponse)
def batch_status(
    user: CurrentUser = Depends(_trigger_roles), conn: psycopg.Connection = Depends(get_db)
) -> BatchStatusResponse:
    return batch_service.get_status(conn, user)


@router.get("/data-freshness", response_model=DataFreshnessResponse)
def data_freshness(
    user: CurrentUser = Depends(get_current_user), conn: psycopg.Connection = Depends(get_db)
) -> DataFreshnessResponse:
    """데이터 지연 배너(RULE-SENSE-04) — 모든 역할이 조회한다."""
    return batch_service.get_data_freshness(conn, user)
