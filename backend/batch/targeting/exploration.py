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
import re
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
    address_of: dict[int, str | None] | None = None,
    same_address_cap: int | None = None,
) -> tuple[list[ScoredCandidate], dict[str, int]]:
    """명부 다양성 상한 — 신호별 상한과 같은 건물(같은 도로명주소) 상한을 함께 건다.

    - 신호별: 주 사유가 상권·거시 신호인 후보는 종류당 top_n×cap_pct%까지만 앞에 싣는다.
      다른 후보로 top_n을 못 채우면 미룬 후보로 채운다.
    - 같은 건물: 주소가 같은 후보는 same_address_cap곳까지만 싣는다. 넘친 후보는 명부에서 빼고
      다음 순위로 채우며, 후보가 모자라면 top_n 미만이 된다.
    점수순은 유지한다. 반환: (재정렬된 후보 목록, 사유별 밀려난 건수 — 같은 건물은 SAME_ADDRESS)
    """
    signal_cap_on = bool(cap_pct and cap_pct > 0 and capped_types)
    address_cap_on = bool(same_address_cap and same_address_cap > 0 and address_of)
    if not signal_cap_on and not address_cap_on:
        return scored, {}
    limit = max(1, int(top_n * cap_pct / 100)) if signal_cap_on and cap_pct else 0
    capped = set(capped_types) if signal_cap_on else set()
    addresses = address_of or {}
    signal_counts: dict[str, int] = {}
    address_counts: dict[str, int] = {}
    address_blocked: set[int] = set()

    def address_key(item: ScoredCandidate) -> str | None:
        return building_key(addresses.get(item.business_id)) if address_cap_on else None

    def address_full(key: str | None) -> bool:
        return key is not None and address_counts.get(key, 0) >= (same_address_cap or 0)

    def take_address(key: str | None) -> None:
        if key is not None:
            address_counts[key] = address_counts.get(key, 0) + 1

    chosen: list[ScoredCandidate] = []
    deferred: list[ScoredCandidate] = []
    for item in scored:
        if len(chosen) >= top_n:
            break
        key = address_key(item)
        if address_full(key):
            address_blocked.add(item.business_id)
            continue
        signal_type = dominant_signal_type(item)
        if signal_type in capped:
            if signal_counts.get(signal_type, 0) >= limit:
                deferred.append(item)
                continue
            signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
        take_address(key)
        chosen.append(item)
    refill: list[ScoredCandidate] = []
    for item in deferred:
        if len(chosen) + len(refill) >= top_n:
            break
        key = address_key(item)
        if address_full(key):
            address_blocked.add(item.business_id)
            continue
        take_address(key)
        refill.append(item)
    head = chosen + refill
    head_ids = {item.business_id for item in head}
    # 밀려난 건수 = 상한이 없었다면 top_n 안에 들었을 후보 중 빠진 것
    pushed: dict[str, int] = {}
    for item in scored[:top_n]:
        if item.business_id not in head_ids:
            reason = "SAME_ADDRESS" if item.business_id in address_blocked else (dominant_signal_type(item) or "")
            pushed[reason] = pushed.get(reason, 0) + 1
    # 같은 건물 상한에 걸린 후보는 뒤에도 남기지 않는다(탐색 슬롯 등 뒤 단계가 다시 넣지 않도록).
    # 뒤 목록도 누적으로 센다 — 같은 건물 후보 여러 곳이 뒤에 함께 남지 않게 한다.
    rest: list[ScoredCandidate] = []
    for item in scored:
        if item.business_id in head_ids or item.business_id in address_blocked:
            continue
        key = address_key(item)
        if address_full(key):
            continue
        take_address(key)
        rest.append(item)
    return head + rest, pushed


_PAREN = re.compile(r"\([^)]*\)")
_SPACES = re.compile(r"\s+")


def building_key(address: str | None) -> str | None:
    """같은 건물 판정 키 — 도로명주소에서 ', 3층'·'(을지로2가)' 같은 상세·참고 항목을 떼고 공백을 정리한다.

    상가정보 주소에는 층·호가 없고, 인허가 주소에는 쉼표 뒤에 층·호가 붙는 경우가 있어 쉼표 앞까지만 비교한다.
    주소가 없으면 None(상한 대상 아님).
    """
    if not address:
        return None
    base = _PAREN.sub(" ", address.split(",", 1)[0])
    key = _SPACES.sub(" ", base).strip()
    return key or None


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
