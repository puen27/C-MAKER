"""SIGNAL 정규화 계약 (normalizers → sensing)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

SignalScope = Literal["BUSINESS", "INDUSTRY", "AREA"]


class SignalWeightEntry(BaseModel):
    """SIGNAL_WEIGHT 1행. industry_code='*'는 신호 전체(상위 계층) 가중치다(RULE-LEARN-03)."""

    signal_type: str
    industry_code: str
    weight: float
    alpha: float = 0
    beta: float = 0
    sample_count: int = 0


class SignalDraft(BaseModel):
    """정규화된 신호 1건. 임계치 미달이어도 원장(SIGNAL)에는 저장한다(RULE-SENSE-03)."""

    snapshot_id: int
    source_name: str
    branch_id: int
    business_id: int | None = None
    signal_type: str
    scope: SignalScope
    target_key: str
    intensity: float = Field(ge=0, le=1)
    raw_value: float
    unit: str
    as_of_date: date  # VAL-09
    detail: dict[str, Any] = Field(default_factory=dict)
    # 업종 단위 신호가 특정 업종을 가리킬 때(INDUSTRY:<업종명>)의 업종명
    industry_name: str | None = None
