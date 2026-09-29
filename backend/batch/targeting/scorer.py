"""스코어링 (RULE-TARGET-02, RULE-TARGET-05). LLM 호출 없음, 순수 함수(TEST-02).

    Score = (Σᵢ wᵢ·sᵢ·aᵢ + R) × 근접도 × 규모적합도

- wᵢ: SIGNAL_WEIGHT(신호×업종). 표본 30건 미만 조합은 신호 전체('*') 가중치를 상속한다(RULE-LEARN-03).
  MVP는 학습 갱신이 비활성이라 초기값 w₀가 그대로 쓰인다 — 값은 DB에서만 읽고 상수로 두지 않는다.
- sᵢ: 이벤트 최신 신호 강도(0~1)
- aᵢ: 적용도. 사업체 신호는 해당 사업체에만 1, 업종 신호는 같은 업종(또는 업종×신호 적합도), 상권 신호는
  반경 내 전체에 업종×신호 적합도로 적용한다.
- R: 신선도 항 = ①인허가 경과일 감쇠 + ②최근 미노출 기간 + ③업종×당일신호 적합도의 가중합(0~1)
"""

from __future__ import annotations

import math
from datetime import date

from backend.batch.targeting.reason_tier import classify_reason_tier
from backend.common.config import PipelineConfig
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.business import BusinessCandidate
from backend.common.schemas.event import ActiveEvent
from backend.common.schemas.recommendation import ScoredCandidate, SignalContribution
from backend.common.schemas.signal import SignalWeightEntry


class WeightTable:
    def __init__(self, entries: list[SignalWeightEntry], *, default_weight: float, min_sample: int) -> None:
        self._specific = {(e.signal_type, e.industry_code): e for e in entries if e.industry_code != "*"}
        self._global = {e.signal_type: e for e in entries if e.industry_code == "*"}
        self._default = default_weight
        self._min_sample = min_sample

    def weight(self, signal_type: str, industry_code: str) -> float:
        specific = self._specific.get((signal_type, industry_code))
        if specific is not None and specific.sample_count >= self._min_sample:
            return specific.weight
        general = self._global.get(signal_type)
        return general.weight if general is not None else self._default

    def global_weights(self) -> dict[str, float]:
        return {signal_type: entry.weight for signal_type, entry in self._global.items()}

    def combo_stats(self, signal_type: str, industry_code: str) -> tuple[float, float, int]:
        """(α, β, 표본수) — 탐색 슬롯 톰슨 샘플링 입력. 행이 없으면 표본 0."""
        entry = self._specific.get((signal_type, industry_code))
        if entry is None:
            return 0.0, 0.0, 0
        return entry.alpha, entry.beta, entry.sample_count

    @property
    def min_sample(self) -> int:
        return self._min_sample


def applicability(event: ActiveEvent, candidate: BusinessCandidate, config: PipelineConfig) -> float:
    if event.scope == "BUSINESS":
        return 1.0 if event.business_id == candidate.id else 0.0
    if event.scope == "INDUSTRY" and event.industry_name:
        return 1.0 if event.industry_name == candidate.industry_name else 0.0
    return config.signal_fit(event.signal_type, candidate.industry_name)


def proximity_factor(distance_km: float, radius_km: float, proximity_min: float) -> float:
    ratio = min(1.0, max(0.0, distance_km / radius_km)) if radius_km > 0 else 1.0
    return 1 - (1 - proximity_min) * ratio


def scale_fit_factor(industry_name: str, primary_industry_tags: list[str], config: PipelineConfig) -> float:
    if any(tag and tag in industry_name for tag in primary_industry_tags):
        return config.scoring.industry_fit_match
    return config.scoring.industry_fit_default


def freshness_terms(
    candidate: BusinessCandidate,
    events: list[ActiveEvent],
    last_exposed_on: date | None,
    target_date: date,
    config: PipelineConfig,
) -> dict[str, float]:
    fresh = config.freshness
    license_term = 0.0
    if candidate.licensed_on is not None:
        days = max(0, (target_date - candidate.licensed_on).days)
        license_term = math.exp(-days / max(fresh.license_decay_days, 1e-9))

    if last_exposed_on is None:
        no_contact_term = 1.0
    else:
        idle = max(0, (target_date - last_exposed_on).days)
        no_contact_term = min(1.0, idle / max(fresh.no_contact_saturation_days, 1e-9))

    signal_fit_term = max(
        (applicability(event, candidate, config) for event in events if event.scope != "BUSINESS"),
        default=0.0,
    )
    total = (
        fresh.weight_license * license_term
        + fresh.weight_no_contact * no_contact_term
        + fresh.weight_signal_fit * signal_fit_term
    )
    return {
        "license": round(license_term, 4),
        "no_contact": round(no_contact_term, 4),
        "signal_fit": round(signal_fit_term, 4),
        "total": round(max(0.0, min(1.0, total)), 4),
    }


def score_candidate(
    branch: BranchContext,
    candidate: BusinessCandidate,
    events: list[ActiveEvent],
    weights: WeightTable,
    last_exposed_on: date | None,
    target_date: date,
    config: PipelineConfig,
) -> ScoredCandidate:
    contributions: list[SignalContribution] = []
    for event in events:
        apply = applicability(event, candidate, config)
        if apply <= 0:
            continue
        weight = weights.weight(event.signal_type, candidate.industry_code)
        contributions.append(
            SignalContribution(
                event_id=event.event_id,
                signal_type=event.signal_type,
                scope=event.scope,
                weight=weight,
                intensity=event.intensity,
                applicability=round(apply, 4),
                contribution=round(weight * event.intensity * apply, 4),
            )
        )
    contributions.sort(key=lambda item: (-item.contribution, item.event_id))
    signal_score = sum(item.contribution for item in contributions)
    fresh = freshness_terms(candidate, events, last_exposed_on, target_date, config)
    proximity = proximity_factor(candidate.distance_km, branch.coverage_radius_km, config.scoring.proximity_min)
    scale_fit = scale_fit_factor(candidate.industry_name, branch.primary_industry_tags, config)
    score = (signal_score + fresh["total"]) * proximity * scale_fit
    return ScoredCandidate(
        business_id=candidate.id,
        industry_code=candidate.industry_code,
        industry_name=candidate.industry_name,
        distance_km=candidate.distance_km,
        signal_score=round(signal_score, 4),
        freshness_score=fresh["total"],
        proximity=round(proximity, 4),
        scale_fit=round(scale_fit, 4),
        score=round(score, 4),
        reason_tier=classify_reason_tier(contributions),
        contributions=contributions,
        freshness_detail=fresh,
    )


def score_candidates(
    branch: BranchContext,
    candidates: list[BusinessCandidate],
    events: list[ActiveEvent],
    weights: WeightTable,
    last_exposure: dict[int, date],
    target_date: date,
    config: PipelineConfig,
) -> list[ScoredCandidate]:
    """배제를 통과한 후보만 받는다. 결과는 점수 내림차순, 동점은 사업체 ID 오름차순(결정론)."""
    scored = [
        score_candidate(branch, candidate, events, weights, last_exposure.get(candidate.id), target_date, config)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: (-item.score, item.business_id))
    return scored
