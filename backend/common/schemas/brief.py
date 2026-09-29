"""BRIEF 생성 계약 (targeting → briefing) 및 API 응답."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.common.schemas.recommendation import ApiModel, RejectedReason, TagStatus

GenerationStatus = Literal["LLM", "TEMPLATE", "REASON_ONLY"]


class BriefFact(BaseModel):
    """출처 태그가 붙은 사실 문장(RULE-BRIEF-01). 판단 레이어가 결정론적으로 만든다."""

    text: str
    source_tag: str  # "소스명·기준일"
    source_name: str
    as_of_date: str


class BriefInput(BaseModel):
    """LLM에 넘기는 확정 결과. 이 값 외의 사실은 인용할 수 없다(RULE-BRIEF-02)."""

    recommendation_id: int
    branch_name: str
    business_name: str
    industry_name: str
    distance_km: float
    facts: list[BriefFact]


class BriefContent(BaseModel):
    recommendation_id: int
    reason_summary: str
    reason_facts: list[BriefFact]
    talk_script: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    generation_status: GenerationStatus
    validation_errors: list[str] = Field(default_factory=list)
    prompt: str | None = None
    model_version: str | None = None
    raw_output: str | None = None
    latency_ms: int | None = None


class BriefFactResponse(ApiModel):
    text: str
    source_tag: str


class BriefResponse(ApiModel):
    recommendation_id: int
    business_name: str
    industry: str
    address: str | None
    distance_label: str
    recommended_on: str
    reason_facts: list[BriefFactResponse]
    script_lines: list[str]
    checklist: list[str]
    generation_status: GenerationStatus
    tag_status: TagStatus
    rejected_reason: RejectedReason | None = None
