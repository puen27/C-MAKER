"""이벤트 승격 판정 — 도메인 정의서 5.1절 순서를 그대로 구현하는 유일한 위치 (4-project-principle.md §2).

1. 임계치 초과 여부 (미달 → SIGNAL로만 저장, RULE-SENSE-03)
2. 동일 대상·동일 신호종류 활성 EVENT가 쿨다운(기본 14일) 내에 있는가 (있으면 병합, RULE-SENSE-01)
3. 지점의 당일 활성 EVENT 수가 상한(기본 8건)에 도달했는가 (초과분은 점수 하위부터 절사, RULE-SENSE-02)
4. 통과하면 EVENT 확정

순수 함수이며 DB·LLM을 호출하지 않는다(TEST-01).
"""

from __future__ import annotations

from datetime import date

from backend.batch.sensing.threshold_engine import exceeds_threshold
from backend.common.schemas.event import ExistingEvent, SignalDecision, event_key
from backend.common.schemas.signal import SignalDraft


def is_within_cooldown(existing_on: date, target_date: date, cooldown_days: int) -> bool:
    """발생일로부터 cooldown_days일이 지나기 전이면 쿨다운 내다 (14일이면 13일 경과까지 병합, 14일째 신규)."""
    elapsed = (target_date - existing_on).days
    return 0 <= elapsed < cooldown_days


def decide_promotions(
    signals: list[SignalDraft],
    *,
    thresholds: dict[str, float],
    existing_events: list[ExistingEvent],
    active_today: int,
    daily_cap: int,
    cooldown_days: int,
    target_date: date,
    signal_weights: dict[str, float],
) -> list[SignalDecision]:
    """한 지점의 당일 신호 목록에 대한 판정. 결과 순서는 입력 순서와 같다."""
    decisions: list[SignalDecision | None] = [None] * len(signals)

    latest_existing: dict[str, ExistingEvent] = {}
    for event in existing_events:
        if not is_within_cooldown(event.occurred_on, target_date, cooldown_days):
            continue
        key = event_key(event.signal_type, event.target_key)
        current = latest_existing.get(key)
        if current is None or (event.occurred_on, event.id) > (current.occurred_on, current.id):
            latest_existing[key] = event

    promotable: list[tuple[int, float]] = []
    for index, signal in enumerate(signals):
        # 1단계 — 임계치
        passed, threshold = exceeds_threshold(signal, thresholds)
        score = round(signal.intensity * signal_weights.get(signal.signal_type, 1.0), 4)
        if not passed:
            decisions[index] = SignalDecision(signal=signal, outcome="BELOW_THRESHOLD",
                                              threshold_value=threshold, event_score=score)
            continue
        # 2단계 — 쿨다운 병합
        existing = latest_existing.get(event_key(signal.signal_type, signal.target_key))
        if existing is not None:
            decisions[index] = SignalDecision(signal=signal, outcome="MERGED", threshold_value=threshold,
                                              merged_event_id=existing.id, event_score=score)
            continue
        decisions[index] = SignalDecision(signal=signal, outcome="PROMOTED", threshold_value=threshold,
                                          event_score=score)
        promotable.append((index, score))

    # 같은 배치 안의 동일 대상·신호종류는 점수가 가장 높은 1건만 이벤트 후보로 남기고 나머지는 병합한다.
    promotable.sort(key=lambda item: (-item[1], signals[item[0]].signal_type, signals[item[0]].target_key, item[0]))
    primary_by_key: dict[str, int] = {}
    unique_candidates: list[int] = []
    for index, _score in promotable:
        key = event_key(signals[index].signal_type, signals[index].target_key)
        if key in primary_by_key:
            decision = decisions[index]
            assert decision is not None
            decisions[index] = decision.model_copy(update={"outcome": "MERGED", "merge_into_batch_key": key})
            continue
        primary_by_key[key] = index
        unique_candidates.append(index)

    # 3단계 — 지점당 일일 상한. 이미 오늘 활성인 이벤트(재실행 등)를 포함해 센다.
    remaining = max(0, daily_cap - active_today)
    for rank, index in enumerate(unique_candidates):
        if rank >= remaining:
            decision = decisions[index]
            assert decision is not None
            decisions[index] = decision.model_copy(update={"outcome": "TRIMMED"})

    return [decision for decision in decisions if decision is not None]
