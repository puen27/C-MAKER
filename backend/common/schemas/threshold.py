"""THRESHOLD_CONFIG API 스키마 (REQ-14, UC-15, VAL-05)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from backend.common.schemas.recommendation import ApiModel


class ThresholdView(ApiModel):
    id: int
    signal_type: str
    category: Literal["SIGNAL", "SYSTEM"]
    label: str
    description: str
    threshold_value: float
    unit: str
    is_fixed: bool
    integer_only: bool
    min_value: float | None
    max_value: float | None
    updated_by_name: str | None
    updated_at: datetime


class ThresholdUpdateRequest(ApiModel):
    threshold_value: float
    # VAL-05: 단위는 대상 지표와 일치해야 한다. 요청에 단위가 오면 저장된 단위와 비교한다.
    unit: str | None = None


class ThresholdHistoryItem(ApiModel):
    id: int
    changed_by_name: str | None
    changed_at: datetime
    before_value: Any
    after_value: Any
