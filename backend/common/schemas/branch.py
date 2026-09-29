"""지점 계약 — 배치가 사용하는 '효력이 발생한' 지점 값(RULE-BRANCH-01)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BranchContext(BaseModel):
    id: int
    branch_code: str
    name: str
    address: str
    lat: float | None
    lng: float | None
    coverage_radius_km: float
    primary_industry_tags: list[str] = Field(default_factory=list)
    handles_forex: bool
    atm_count: int
    # 배치 기준 시각에 BRANCH 현재 값이 아니라 BRANCH_HISTORY의 옛 값이 쓰였는지
    from_history: bool = False

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lng is not None
