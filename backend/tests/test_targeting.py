"""TEST-02: 배제 우선순위(RULE-TARGET-01), 스코어링 공식(RULE-TARGET-02/05), 사유 계층(06), TOP 20·탐색 슬롯(03)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from backend.batch.targeting.exclusion import ExclusionParams, apply_exclusions, exclusion_reason
from backend.batch.targeting.exploration import assemble_recommendations, exploration_seed
from backend.batch.targeting.reason_tier import area_reason_ratio, classify_reason_tier
from backend.batch.targeting.scorer import (
    WeightTable,
    freshness_terms,
    proximity_factor,
    score_candidate,
    score_candidates,
)
from backend.common.config import get_pipeline_config
from backend.common.schemas.recommendation import ScoredCandidate, SignalContribution
from backend.tests.factories import TODAY, active_event, branch, candidate, tag, weights

PARAMS = ExclusionParams(
    contact_cooldown_days=30,
    reject_exclusion_days={"ALREADY_CUSTOMER": 0, "NOT_TARGET": 0, "INFO_ERROR": 90, "UNREACHABLE": 0},
)


# ─────────────── 배제 ───────────────

@pytest.mark.parametrize("status", ["휴업", "폐업", "영업정지"])
def test_non_operating_business_is_excluded(status):
    assert exclusion_reason(candidate(1, operating_status=status), [], TODAY, PARAMS) == "OPERATING_STATUS"


def test_operating_status_takes_priority_over_tag_history():
    history = [tag(1, "REJECTED", TODAY, "UNREACHABLE")]
    assert exclusion_reason(candidate(1, operating_status="폐업"), history, TODAY, PARAMS) == "OPERATING_STATUS"


def test_contact_cooldown_boundary():
    assert exclusion_reason(candidate(1), [tag(1, "VISITED", TODAY - timedelta(days=29))], TODAY, PARAMS) == (
        "CONTACT_COOLDOWN")
    assert exclusion_reason(candidate(1), [tag(1, "VISITED", TODAY - timedelta(days=30))], TODAY, PARAMS) is None


def test_hold_tag_does_not_exclude():
    assert exclusion_reason(candidate(1), [tag(1, "HOLD", TODAY)], TODAY, PARAMS) is None


def test_permanent_rejection_never_expires():
    history = [tag(1, "REJECTED", TODAY - timedelta(days=900), "ALREADY_CUSTOMER")]
    assert exclusion_reason(candidate(1), history, TODAY, PARAMS) == "REJECTED"


def test_temporary_rejection_expires():
    recent = [tag(1, "REJECTED", TODAY - timedelta(days=89), "INFO_ERROR")]
    expired = [tag(1, "REJECTED", TODAY - timedelta(days=90), "INFO_ERROR")]
    assert exclusion_reason(candidate(1), recent, TODAY, PARAMS) == "REJECTED"
    assert exclusion_reason(candidate(1), expired, TODAY, PARAMS) is None


def test_unreachable_is_treated_as_opt_out():
    history = [tag(1, "REJECTED", TODAY - timedelta(days=400), "UNREACHABLE")]
    assert exclusion_reason(candidate(1), history, TODAY, PARAMS) == "OPT_OUT"


def test_contact_cooldown_precedes_rejection():
    history = [tag(1, "VISITED", TODAY - timedelta(days=1)), tag(1, "REJECTED", TODAY, "NOT_TARGET")]
    assert exclusion_reason(candidate(1), history, TODAY, PARAMS) == "CONTACT_COOLDOWN"


def test_apply_exclusions_counts_and_keeps_order():
    candidates = [candidate(1), candidate(2, operating_status="폐업"), candidate(3), candidate(4)]
    history = [tag(3, "REJECTED", TODAY, "UNREACHABLE"), tag(4, "VISITED", TODAY)]
    passed, counts = apply_exclusions(candidates, history, TODAY, PARAMS)
    assert [c.id for c in passed] == [1]
    assert counts == {"OPERATING_STATUS": 1, "CONTACT_COOLDOWN": 1, "REJECTED": 0, "OPT_OUT": 1}


# ─────────────── 스코어링 ───────────────

CONFIG = get_pipeline_config()
TABLE = WeightTable(
    weights(("AREA_NEW_OPENINGS", "*", 0.6, 0), ("NEW_BUSINESS_OPENING", "*", 1.5, 0),
            ("NEW_BUSINESS_OPENING", "I201", 1.9, 10)),
    default_weight=1.0, min_sample=30,
)


def test_weight_inherits_global_when_sample_below_30():
    assert TABLE.weight("NEW_BUSINESS_OPENING", "I201") == 1.5
    table = WeightTable(weights(("NEW_BUSINESS_OPENING", "*", 1.5, 0), ("NEW_BUSINESS_OPENING", "I201", 1.9, 30)),
                        default_weight=1.0, min_sample=30)
    assert table.weight("NEW_BUSINESS_OPENING", "I201") == 1.9
    assert table.weight("UNKNOWN", "I201") == 1.0


def test_proximity_is_linear_between_branch_and_radius_edge():
    assert proximity_factor(0, 1.5, 0.5) == 1.0
    assert proximity_factor(1.5, 1.5, 0.5) == 0.5
    assert proximity_factor(0.75, 1.5, 0.5) == pytest.approx(0.75)
    assert proximity_factor(9, 1.5, 0.5) == 0.5


def test_freshness_terms_and_normalization():
    fresh = CONFIG.freshness
    item = candidate(1, licensed_on=TODAY - timedelta(days=int(fresh.license_decay_days)))
    terms = freshness_terms(item, [], None, TODAY, CONFIG)
    assert terms["license"] == pytest.approx(math.exp(-1), abs=1e-4)
    assert terms["no_contact"] == 1.0  # 명부 노출 이력 없음
    assert terms["signal_fit"] == 0.0
    assert 0 <= terms["total"] <= 1

    recently = freshness_terms(candidate(1), [], TODAY - timedelta(days=3), TODAY, CONFIG)
    assert recently["no_contact"] == pytest.approx(3 / fresh.no_contact_saturation_days, abs=1e-4)


def test_score_formula_matches_rule_target_02():
    b = branch()
    item = candidate(1, distance_km=0.75, industry_name="음식·한식")
    events = [
        active_event(10, signal_type="NEW_BUSINESS_OPENING", scope="BUSINESS", target_key="BUSINESS:1",
                     business_id=1, intensity=0.8),
        active_event(11, intensity=0.5),  # AREA_NEW_OPENINGS, 업종 적합도 '*'=0.5
    ]
    scored = score_candidate(b, item, events, TABLE, None, TODAY, CONFIG)
    expected_signal = 1.5 * 0.8 * 1.0 + 0.6 * 0.5 * 0.5
    assert scored.signal_score == pytest.approx(expected_signal, abs=1e-4)
    proximity = 1 - 0.5 * (0.75 / 1.5)
    scale_fit = CONFIG.scoring.industry_fit_match  # 지점 주력 '음식'과 일치
    assert scored.score == pytest.approx((expected_signal + scored.freshness_score) * proximity * scale_fit, abs=1e-3)
    assert scored.reason_tier == "BUSINESS"


def test_business_signal_applies_only_to_its_business():
    events = [active_event(10, signal_type="NEW_BUSINESS_OPENING", scope="BUSINESS", target_key="BUSINESS:1",
                           business_id=1, intensity=1.0)]
    other = score_candidate(branch(), candidate(2), events, TABLE, None, TODAY, CONFIG)
    assert other.signal_score == 0
    assert other.reason_tier == "AREA"  # R만으로 선정 → 상권 사유(RULE-TARGET-05)


def test_industry_opening_signal_applies_to_same_industry_only():
    events = [active_event(20, signal_type="INDUSTRY_NEW_OPENINGS", scope="INDUSTRY",
                           target_key="INDUSTRY:음식·한식", industry_name="음식·한식", intensity=0.4)]
    same = score_candidate(branch(), candidate(1, industry_name="음식·한식"), events, TABLE, None, TODAY, CONFIG)
    diff = score_candidate(branch(), candidate(2, industry_name="소매·편의점"), events, TABLE, None, TODAY, CONFIG)
    assert same.reason_tier == "INDUSTRY" and same.signal_score > 0
    assert diff.signal_score == 0


def test_score_candidates_is_deterministic_on_ties():
    items = [candidate(3), candidate(1), candidate(2)]
    scored = score_candidates(branch(), items, [], TABLE, {}, TODAY, CONFIG)
    assert [s.business_id for s in scored] == [1, 2, 3]


def test_reason_tier_priority_and_ratio():
    def contribution(scope, value):
        return SignalContribution(event_id=1, signal_type="X", scope=scope, weight=1, intensity=1,
                                  applicability=1, contribution=value)

    assert classify_reason_tier([contribution("AREA", 1), contribution("INDUSTRY", 1)]) == "INDUSTRY"
    assert classify_reason_tier([contribution("BUSINESS", 0)]) == "AREA"
    assert area_reason_ratio(["AREA", "AREA", "BUSINESS", "INDUSTRY"]) == 50.0
    assert area_reason_ratio([]) == 0.0


# ─────────────── TOP 20 + 탐색 슬롯 ───────────────

def _scored(business_id: int, score: float, with_signal: bool = True) -> ScoredCandidate:
    contributions = [SignalContribution(event_id=1, signal_type="AREA_NEW_OPENINGS", scope="AREA", weight=1,
                                        intensity=0.5, applicability=1, contribution=0.5)] if with_signal else []
    return ScoredCandidate(business_id=business_id, industry_code="I201", industry_name="음식", distance_km=0.1,
                           signal_score=0.5, freshness_score=0.5, proximity=1, scale_fit=1, score=score,
                           reason_tier="AREA", contributions=contributions)


POOL = [_scored(i, 100 - i) for i in range(1, 41)]


def test_top20_without_exploration_is_score_order():
    ranked = assemble_recommendations(POOL, top_n=20, exploration_slots=3, exploration_enabled=False,
                                      weights=TABLE, seed=1)
    assert [r.candidate.business_id for r in ranked] == list(range(1, 21))
    assert [r.rank for r in ranked] == list(range(1, 21))
    assert not any(r.is_exploration_slot for r in ranked)


def test_top20_includes_exactly_three_exploration_slots_when_enabled():
    seed = exploration_seed(1, TODAY)
    ranked = assemble_recommendations(POOL, top_n=20, exploration_slots=3, exploration_enabled=True,
                                      weights=TABLE, seed=seed)
    assert len(ranked) == 20  # 20 + 3 = 23이 아니다
    assert sum(r.is_exploration_slot for r in ranked) == 3
    exploit_ids = {r.candidate.business_id for r in ranked if not r.is_exploration_slot}
    assert exploit_ids == set(range(1, 18))
    # 같은 시드 → 같은 명부 (재현성)
    again = assemble_recommendations(POOL, top_n=20, exploration_slots=3, exploration_enabled=True,
                                     weights=TABLE, seed=seed)
    assert [r.candidate.business_id for r in again] == [r.candidate.business_id for r in ranked]


def test_exploration_fills_remaining_slots_by_score_when_pool_lacks_signals():
    pool = [_scored(i, 100 - i, with_signal=i <= 17) for i in range(1, 30)]
    ranked = assemble_recommendations(pool, top_n=20, exploration_slots=3, exploration_enabled=True,
                                      weights=TABLE, seed=7)
    assert len(ranked) == 20
    assert sum(r.is_exploration_slot for r in ranked) == 0


def test_short_candidate_list_returns_all():
    ranked = assemble_recommendations(POOL[:5], top_n=20, exploration_slots=3, exploration_enabled=False,
                                      weights=TABLE, seed=1)
    assert len(ranked) == 5


def test_exploration_seed_is_stable():
    assert exploration_seed(1, date(2026, 9, 29)) == exploration_seed(1, date(2026, 9, 29))
    assert exploration_seed(1, date(2026, 9, 29)) != exploration_seed(2, date(2026, 9, 29))
