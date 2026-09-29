"""RECOMMENDATION 계약 (targeting 산출물) 및 API 응답 스키마."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.common.schemas.signal import SignalScope

TagStatus = Literal["UNTAGGED", "VISITED", "HOLD", "REJECTED"]
TagValue = Literal["VISITED", "HOLD", "REJECTED"]
RejectedReason = Literal["ALREADY_CUSTOMER", "NOT_TARGET", "INFO_ERROR", "UNREACHABLE"]


class ApiModel(BaseModel):
    """API 요청/응답은 camelCase JSON (프론트엔드 타입과 일치)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


# ───────────── 배치 계약 ─────────────


class SignalContribution(BaseModel):
    event_id: int
    signal_type: str
    scope: SignalScope
    weight: float
    intensity: float
    applicability: float
    contribution: float


class ScoredCandidate(BaseModel):
    """배제를 통과한 후보 1건의 점수 (RULE-TARGET-02: Score = (Σ wᵢ·sᵢ + R) × 근접도 × 규모적합도)."""

    business_id: int
    industry_code: str
    industry_name: str
    distance_km: float
    signal_score: float
    freshness_score: float = Field(ge=0, le=1)
    proximity: float
    scale_fit: float
    score: float
    reason_tier: SignalScope
    contributions: list[SignalContribution] = Field(default_factory=list)
    freshness_detail: dict[str, float] = Field(default_factory=dict)


class RankedRecommendation(BaseModel):
    candidate: ScoredCandidate
    rank: int
    is_exploration_slot: bool


# ───────────── API 응답 ─────────────


class RecommendationItem(ApiModel):
    """GET /api/recommendations 항목 (docs/10-implementation-guide.md §6.3). 탐색 슬롯 여부는 내려주지 않는다(RULE-TARGET-04)."""

    id: int
    rank: int
    business_name: str
    industry: str
    score: float
    reason_summary: str
    reason_source_tag: str
    tag_status: TagStatus
    rejected_reason: RejectedReason | None = None
    carried_over_from_yesterday: bool


class RecommendationSummary(ApiModel):
    """대시보드 상단 배너용 요약 (UC-09 어제 미태깅, RULE-TARGET-06 상권사유비율, RULE-SENSE-02 외 N건)."""

    date: date
    total: int
    untagged_count: int
    yesterday_untagged_count: int
    area_reason_ratio: float
    area_reason_ratio_limit: float
    area_reason_ratio_exceeded: bool
    active_event_count: int
    trimmed_event_count: int


class TagRequest(ApiModel):
    tag_status: TagValue
    rejected_reason: RejectedReason | None = None


class TagResponse(ApiModel):
    recommendation_id: int
    tag_status: TagStatus
    rejected_reason: RejectedReason | None = None
