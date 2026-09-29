"""테스트용 값 생성기. 상호명은 실제 사업자와 무관한 가상 예시명이다(개인정보 없음)."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.common.schemas.branch import BranchContext
from backend.common.schemas.brief import BriefFact
from backend.common.schemas.business import BusinessCandidate, TagHistoryEntry
from backend.common.schemas.event import ActiveEvent, ExistingEvent
from backend.common.schemas.signal import SignalDraft, SignalWeightEntry

TODAY = date(2026, 9, 29)


def branch(**overrides: Any) -> BranchContext:
    values: dict[str, Any] = {
        "id": 1, "branch_code": "000101", "name": "강남중앙지점", "address": "서울특별시 강남구 테헤란로 152",
        "lat": 37.5000, "lng": 127.0360, "coverage_radius_km": 1.5, "primary_industry_tags": ["음식"],
        "handles_forex": True, "atm_count": 4,
    }
    values.update(overrides)
    return BranchContext(**values)


def signal(**overrides: Any) -> SignalDraft:
    values: dict[str, Any] = {
        "snapshot_id": 1, "source_name": "PERMIT_DAILY", "branch_id": 1, "signal_type": "AREA_NEW_OPENINGS",
        "scope": "AREA", "target_key": "AREA", "intensity": 0.5, "raw_value": 5, "unit": "건/일",
        "as_of_date": TODAY,
    }
    values.update(overrides)
    return SignalDraft(**values)


def existing_event(event_id: int, signal_type: str, target_key: str, occurred_on: date) -> ExistingEvent:
    return ExistingEvent(id=event_id, signal_type=signal_type, target_key=target_key, occurred_on=occurred_on)


def candidate(business_id: int, **overrides: Any) -> BusinessCandidate:
    values: dict[str, Any] = {
        "id": business_id, "name": f"예시상점{business_id:02d}", "industry_code": "I201",
        "industry_name": "음식·한식", "address": None, "lat": 37.5, "lng": 127.036, "distance_km": 0.5,
        "operating_status": "정상", "status_source": "SBIZ", "licensed_on": None,
        "population_as_of": date(2026, 9, 1),
    }
    values.update(overrides)
    return BusinessCandidate(**values)


def tag(business_id: int, tag_value: str, tagged_on: date, reject_reason: str | None = None) -> TagHistoryEntry:
    return TagHistoryEntry(business_id=business_id, tag_value=tag_value, reject_reason=reject_reason,
                           tagged_on=tagged_on)


def active_event(event_id: int, **overrides: Any) -> ActiveEvent:
    values: dict[str, Any] = {
        "event_id": event_id, "signal_type": "AREA_NEW_OPENINGS", "scope": "AREA", "target_key": "AREA",
        "business_id": None, "industry_name": None, "intensity": 0.5, "raw_value": 5, "unit": "건/일",
        "as_of_date": TODAY, "source_name": "PERMIT_DAILY", "detail": {"count": 5, "radius_km": 1.5},
    }
    values.update(overrides)
    return ActiveEvent(**values)


def weights(*entries: tuple[str, str, float, int]) -> list[SignalWeightEntry]:
    return [
        SignalWeightEntry(signal_type=s, industry_code=i, weight=w, sample_count=n) for s, i, w, n in entries
    ]


def fact(text: str, source: str = "지방행정인허가", as_of: str = "2026-09-27") -> BriefFact:
    return BriefFact(text=text, source_tag=f"{source}·{as_of}", source_name=source, as_of_date=as_of)
