"""BUSINESS 모집단 적재 계약 (REQ-16, UC-17)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

OperatingStatus = Literal["정상", "휴업", "폐업", "영업정지"]
StatusSource = Literal["PERMIT", "SBIZ", "NTS"]


class PermitRecord(BaseModel):
    """지방행정 인허가 원본 1행(전수 CSV 또는 변동분 API)을 공통 필드로 옮긴 값. 좌표는 원본 좌표계 그대로."""

    mgt_no: str
    name: str
    industry_code: str = ""
    industry_name: str = ""
    operating_status: OperatingStatus
    licensed_on: date | None = None
    closed_on: date | None = None
    x: float | None = None
    y: float | None = None
    address: str | None = None
    update_type: str | None = None  # I(신규)/U(변경)/D(삭제) — 변동분 API만


class BusinessRecord(BaseModel):
    """BUSINESS 테이블에 병합(upsert)할 값. 좌표는 WGS84로 변환된 상태여야 한다(VAL-11)."""

    permit_mgt_no: str | None = None
    sbiz_store_id: str | None = None
    name: str
    industry_code: str = ""
    industry_name: str = ""
    address: str | None = None
    lat: float = Field(ge=33, le=39)
    lng: float = Field(ge=124, le=132)
    source_crs: str
    biz_reg_no: str | None = Field(default=None, pattern=r"^[0-9]{10}$")
    operating_status: OperatingStatus
    status_source: StatusSource
    licensed_on: date | None = None
    population_as_of: date


class BusinessCandidate(BaseModel):
    """targeting 단계 입력 — 지점 담당 반경 안의 사업체."""

    id: int
    name: str
    industry_code: str
    industry_name: str
    address: str | None
    lat: float
    lng: float
    distance_km: float
    operating_status: OperatingStatus
    status_source: StatusSource
    licensed_on: date | None
    population_as_of: date


class TagHistoryEntry(BaseModel):
    """배제 판정 입력 — 사업체 단위 태깅 이력(RULE-TARGET-01). 태깅 계정 정보는 담지 않는다(CLAUDE.md §0.7)."""

    business_id: int
    tag_value: Literal["VISITED", "HOLD", "REJECTED"]
    reject_reason: str | None
    tagged_on: date
