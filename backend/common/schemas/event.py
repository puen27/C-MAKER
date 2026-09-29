"""EVENT 승격 판정 계약 (sensing → targeting)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from backend.common.schemas.signal import SignalDraft, SignalScope

PromotionOutcome = Literal["BELOW_THRESHOLD", "MERGED", "PROMOTED", "TRIMMED"]


class ExistingEvent(BaseModel):
    """쿨다운 판정에 쓰는 기존 활성 이벤트."""

    id: int
    signal_type: str
    target_key: str
    occurred_on: date


class SignalDecision(BaseModel):
    """신호 1건에 대한 5.1절 판정 결과."""

    signal: SignalDraft
    outcome: PromotionOutcome
    threshold_value: float | None = None
    # 쿨다운 내 기존 이벤트에 병합되는 경우의 대상 이벤트 ID
    merged_event_id: int | None = None
    # 같은 배치 안에서 같은 대상·신호종류가 먼저 판정된 경우, 그 판정의 이벤트로 병합한다
    merge_into_batch_key: str | None = None
    event_score: float = 0.0

    @property
    def event_key(self) -> str:
        return event_key(self.signal.signal_type, self.signal.target_key)


def event_key(signal_type: str, target_key: str) -> str:
    """5.1절 '동일 대상·동일 신호종류' 판정 키."""
    return f"{signal_type}|{target_key}"


class ActiveEvent(BaseModel):
    """스코어링에 쓰는 활성 이벤트와 그 최신 신호."""

    event_id: int
    signal_type: str
    scope: SignalScope
    target_key: str
    business_id: int | None
    industry_name: str | None
    intensity: float
    raw_value: float
    unit: str
    as_of_date: date
    source_name: str
    detail: dict
