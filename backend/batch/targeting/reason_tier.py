"""선정 사유 계층 분류 (RULE-TARGET-06).

① 사업체 사유(BUSINESS) > ② 업종 사유(INDUSTRY) > ③ 상권 사유(AREA). 기여한 신호 중 가장 구체적인 계층을
사유 계층으로 삼는다. 신호 기여 없이 신선도 항 R만으로 선정된 항목은 ③(AREA)이다(RULE-TARGET-05).
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.common.schemas.recommendation import SignalContribution
from backend.common.schemas.signal import SignalScope

_TIER_ORDER: tuple[SignalScope, ...] = ("BUSINESS", "INDUSTRY", "AREA")


def classify_reason_tier(contributions: Iterable[SignalContribution]) -> SignalScope:
    scopes = {item.scope for item in contributions if item.contribution > 0}
    for tier in _TIER_ORDER:
        if tier in scopes:
            return tier
    return "AREA"


def area_reason_ratio(tiers: list[str]) -> float:
    """지점·일자별 '③만 가진 항목'의 비율(%). 명부가 비어 있으면 0."""
    if not tiers:
        return 0.0
    return round(sum(1 for tier in tiers if tier == "AREA") / len(tiers) * 100, 1)
