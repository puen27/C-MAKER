"""TOP 20 확정과 탐색 슬롯 배정 (RULE-TARGET-03/04, RULE-LEARN-04).

"TOP 20"은 탐색 슬롯 3건을 포함한 총 20건이다(20+3=23이 아님). 탐색 슬롯은 처음부터 분리 설계한다:
상위 (20-3)건을 점수순으로 고르고, 나머지 후보 중 표본이 부족한 신호×업종 조합을 톰슨 샘플링으로 3건 뽑는다.

- MVP(CLAUDE.md §9)에서는 `exploration_enabled=false` — 슬롯 3자리를 일반 점수순 후보로 채운다.
- 톰슨 샘플링 난수는 (지점, 일자)로 시드를 고정해 같은 입력이면 같은 명부가 나온다(PRIN-08 재현성).
- 탐색 슬롯 여부는 화면에 노출하지 않고 RECOMMENDATION.is_exploration_slot으로 내부 집계에만 쓴다.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date

from backend.batch.targeting.scorer import WeightTable
from backend.common.schemas.recommendation import RankedRecommendation, ScoredCandidate


def exploration_seed(branch_id: int, target_date: date) -> int:
    digest = hashlib.sha256(f"{branch_id}:{target_date.isoformat()}".encode()).hexdigest()
    return int(digest[:16], 16)


def select_exploration_slots(
    pool: list[ScoredCandidate],
    n_slots: int,
    weights: WeightTable,
    seed: int,
) -> list[ScoredCandidate]:
    """표본 부족(n < min_sample) 조합을 가진 후보에서 Beta(α+1, β+1) 표본값이 큰 순으로 고른다."""
    rng = random.Random(seed)
    draws: list[tuple[float, int, ScoredCandidate]] = []
    for candidate in pool:  # pool은 점수순으로 정렬되어 있어 난수 소비 순서가 결정적이다
        if not candidate.contributions:
            continue
        dominant = candidate.contributions[0]
        alpha, beta, samples = weights.combo_stats(dominant.signal_type, candidate.industry_code)
        if samples >= weights.min_sample:
            continue
        draws.append((rng.betavariate(alpha + 1, beta + 1), candidate.business_id, candidate))
    draws.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _draw, _id, candidate in draws[:n_slots]]


def dominant_signal_type(candidate: ScoredCandidate) -> str | None:
    """주 사유 신호(기여도 1위). 브리프 첫 근거 문장도 같은 신호에서 나온다."""
    return candidate.contributions[0].signal_type if candidate.contributions else None


def apply_signal_share_cap(
    scored: list[ScoredCandidate],
    *,
    top_n: int,
    cap_pct: float | None,
    capped_types: list[str],
) -> tuple[list[ScoredCandidate], dict[str, int]]:
    """신호별 명부 상한 — 주 사유가 상권·거시 신호인 후보는 종류당 top_n×cap_pct%까지만 앞에 싣는다.

    점수순을 유지한 채 상한을 넘는 후보를 뒤로 미룬다. 다른 후보로 top_n을 못 채우면 미룬 후보로 채운다.
    반환: (재정렬된 후보 목록, 신호종류별 밀려난 건수)
    """
    if not cap_pct or cap_pct <= 0 or not capped_types:
        return scored, {}
    limit = max(1, int(top_n * cap_pct / 100))
    capped = set(capped_types)
    counts: dict[str, int] = {}
    chosen: list[ScoredCandidate] = []
    deferred: list[ScoredCandidate] = []
    for item in scored:
        if len(chosen) >= top_n:
            break
        signal_type = dominant_signal_type(item)
        if signal_type in capped:
            if counts.get(signal_type, 0) >= limit:
                deferred.append(item)
                continue
            counts[signal_type] = counts.get(signal_type, 0) + 1
        chosen.append(item)
    refill = deferred[: max(0, top_n - len(chosen))]
    head = chosen + refill
    head_ids = {item.business_id for item in head}
    # 밀려난 건수 = 상한이 없었다면 top_n 안에 들었을 후보 중 빠진 것
    pushed: dict[str, int] = {}
    for item in scored[:top_n]:
        if item.business_id not in head_ids:
            signal_type = dominant_signal_type(item) or ""
            pushed[signal_type] = pushed.get(signal_type, 0) + 1
    return head + [item for item in scored if item.business_id not in head_ids], pushed


def assemble_recommendations(
    scored: list[ScoredCandidate],
    *,
    top_n: int,
    exploration_slots: int,
    exploration_enabled: bool,
    weights: WeightTable,
    seed: int,
) -> list[RankedRecommendation]:
    """점수순 정렬된 후보 → 최대 top_n건의 순위 확정 목록."""
    slots = exploration_slots if exploration_enabled else 0
    exploit = scored[: max(0, top_n - slots)]
    chosen_ids = {item.business_id for item in exploit}
    explore: list[ScoredCandidate] = []
    if slots:
        pool = [item for item in scored if item.business_id not in chosen_ids]
        explore = select_exploration_slots(pool, slots, weights, seed)
        chosen_ids.update(item.business_id for item in explore)
        # 표본 부족 조합이 모자라면 남은 자리는 점수순으로 채운다(총 20건 보장).
        for item in scored:
            if len(exploit) + len(explore) >= top_n:
                break
            if item.business_id not in chosen_ids:
                exploit.append(item)
                chosen_ids.add(item.business_id)

    explore_ids = {item.business_id for item in explore}
    final = sorted(exploit + explore, key=lambda item: (-item.score, item.business_id))[:top_n]
    return [
        RankedRecommendation(candidate=item, rank=index + 1, is_exploration_slot=item.business_id in explore_ids)
        for index, item in enumerate(final)
    ]
