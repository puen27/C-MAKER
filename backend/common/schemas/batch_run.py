"""BATCH_RUN 및 데이터 신선도 API 스키마 (REQ-17, UC-18, RULE-SENSE-04)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from backend.common.schemas.recommendation import ApiModel

BatchRunStatus = Literal["RUNNING", "SUCCESS", "FAILED"]
BatchRunType = Literal["SCHEDULED", "MANUAL"]


class BatchRunView(ApiModel):
    id: int
    run_type: BatchRunType
    status: BatchRunStatus
    target_date: date
    triggered_by_name: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expected_completion_at: datetime | None = None
    failure_reason: str | None = None


class BatchStatusResponse(ApiModel):
    latest_run: BatchRunView | None
    # 요청 계정 기준 VAL-12 쿨다운 잔여 시간(초). 0이면 즉시 요청 가능.
    cooldown_remaining_seconds: int
    cooldown_minutes: int


class BatchTriggerResponse(ApiModel):
    run: BatchRunView
    # RULE-SENSE-06: 이미 RUNNING인 실행이 있으면 새로 만들지 않고 기존 실행을 돌려준다.
    already_running: bool


SourceStatus = Literal["FRESH", "FALLBACK", "DEGRADED", "UNAVAILABLE", "SKIPPED"]


class SourceFreshness(ApiModel):
    source_name: str
    display_name: str
    status: SourceStatus
    latest_as_of_date: date | None
    expected_as_of_date: date
    delay_days: int
    is_fallback: bool


class DataFreshnessResponse(ApiModel):
    reference_date: date
    # 배너 노출 여부 — 소스 수집 불가·지연, 배치 실패/미완료, 오늘 명부 미생성인 경우
    delayed: bool
    max_delay_days: int
    todays_list_ready: bool
    latest_run_status: BatchRunStatus | None
    message: str | None
    sources: list[SourceFreshness]
