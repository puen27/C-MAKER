"""TEST-01: 이벤트 승격 판정(도메인 정의서 5.1절) — 임계치 경계, 쿨다운 경계, 상한 절사."""

from __future__ import annotations

from datetime import timedelta

from backend.batch.sensing.event_promoter import decide_promotions, is_within_cooldown
from backend.tests.factories import TODAY, existing_event, signal

THRESHOLDS = {"AREA_NEW_OPENINGS": 3.0, "NEW_BUSINESS_OPENING": 0.0, "FX_DAILY_CHANGE": 1.0}


def decide(signals, *, existing=(), active_today=0, cap=8, cooldown=14):
    return decide_promotions(
        list(signals), thresholds=THRESHOLDS, existing_events=list(existing), active_today=active_today,
        daily_cap=cap, cooldown_days=cooldown, target_date=TODAY, signal_weights={},
    )


# ── 1단계: 임계치 ──

def test_below_threshold_is_not_promoted():
    [decision] = decide([signal(raw_value=2)])
    assert decision.outcome == "BELOW_THRESHOLD"


def test_equal_to_threshold_is_not_promoted_because_rule_requires_exceeding():
    [decision] = decide([signal(raw_value=3)])
    assert decision.outcome == "BELOW_THRESHOLD"
    assert decision.threshold_value == 3.0


def test_just_above_threshold_is_promoted():
    [decision] = decide([signal(raw_value=3.0001)])
    assert decision.outcome == "PROMOTED"


def test_signal_type_without_threshold_is_never_promoted():
    [decision] = decide([signal(signal_type="UNKNOWN_SIGNAL", raw_value=999)])
    assert decision.outcome == "BELOW_THRESHOLD"
    assert decision.threshold_value is None


# ── 2단계: 쿨다운 병합 ──

def test_cooldown_boundary():
    assert is_within_cooldown(TODAY - timedelta(days=13), TODAY, 14)
    assert not is_within_cooldown(TODAY - timedelta(days=14), TODAY, 14)
    assert is_within_cooldown(TODAY, TODAY, 14)


def test_recurrence_within_cooldown_merges_into_existing_event():
    existing = [existing_event(77, "AREA_NEW_OPENINGS", "AREA", TODAY - timedelta(days=13))]
    [decision] = decide([signal(raw_value=5)], existing=existing)
    assert decision.outcome == "MERGED"
    assert decision.merged_event_id == 77


def test_recurrence_after_cooldown_creates_new_event():
    existing = [existing_event(77, "AREA_NEW_OPENINGS", "AREA", TODAY - timedelta(days=14))]
    [decision] = decide([signal(raw_value=5)], existing=existing)
    assert decision.outcome == "PROMOTED"


def test_cooldown_is_per_target_and_signal_type():
    existing = [existing_event(77, "AREA_NEW_OPENINGS", "AREA", TODAY - timedelta(days=1))]
    decisions = decide([
        signal(signal_type="NEW_BUSINESS_OPENING", scope="BUSINESS", target_key="BUSINESS:1", raw_value=1),
    ], existing=existing)
    assert decisions[0].outcome == "PROMOTED"


def test_below_threshold_signal_is_not_merged_even_within_cooldown():
    existing = [existing_event(77, "AREA_NEW_OPENINGS", "AREA", TODAY - timedelta(days=1))]
    [decision] = decide([signal(raw_value=1)], existing=existing)
    assert decision.outcome == "BELOW_THRESHOLD"
    assert decision.merged_event_id is None


def test_duplicates_in_same_batch_become_one_event():
    decisions = decide([signal(raw_value=5, intensity=0.4), signal(raw_value=6, intensity=0.9, snapshot_id=2)])
    outcomes = sorted(d.outcome for d in decisions)
    assert outcomes == ["MERGED", "PROMOTED"]
    merged = next(d for d in decisions if d.outcome == "MERGED")
    assert merged.merge_into_batch_key == "AREA_NEW_OPENINGS|AREA"
    promoted = next(d for d in decisions if d.outcome == "PROMOTED")
    assert promoted.signal.intensity == 0.9  # 점수가 높은 쪽이 이벤트가 된다


# ── 3단계: 지점당 일일 상한 ──

def _business_signals(count: int):
    return [
        signal(signal_type="NEW_BUSINESS_OPENING", scope="BUSINESS", target_key=f"BUSINESS:{i}", raw_value=1,
               intensity=round(0.1 + i * 0.05, 3))
        for i in range(count)
    ]


def test_cap_trims_lowest_scores():
    decisions = decide(_business_signals(10), cap=8)
    promoted = [d for d in decisions if d.outcome == "PROMOTED"]
    trimmed = [d for d in decisions if d.outcome == "TRIMMED"]
    assert len(promoted) == 8 and len(trimmed) == 2
    assert max(d.signal.intensity for d in trimmed) < min(d.signal.intensity for d in promoted)


def test_cap_exactly_reached_trims_nothing():
    decisions = decide(_business_signals(8), cap=8)
    assert all(d.outcome == "PROMOTED" for d in decisions)


def test_cap_counts_events_already_active_today():
    decisions = decide(_business_signals(5), cap=8, active_today=6)
    assert sum(d.outcome == "PROMOTED" for d in decisions) == 2
    assert sum(d.outcome == "TRIMMED" for d in decisions) == 3


def test_merged_signals_do_not_consume_cap():
    existing = [existing_event(1, "NEW_BUSINESS_OPENING", "BUSINESS:0", TODAY - timedelta(days=2))]
    decisions = decide(_business_signals(3), existing=existing, cap=2)
    assert [d.outcome for d in decisions].count("MERGED") == 1
    assert [d.outcome for d in decisions].count("PROMOTED") == 2


def test_output_order_matches_input_order():
    signals = _business_signals(4)
    decisions = decide(signals, cap=2)
    assert [d.signal.target_key for d in decisions] == [s.target_key for s in signals]
