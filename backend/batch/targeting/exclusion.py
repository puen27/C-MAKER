"""배제 필터 (RULE-TARGET-01) — 스코어링보다 먼저 수행한다.

우선순위: 영업상태(인허가 1차 / 국세청 확인 시 덮어씀) > 상호 없음(INVALID_NAME) > 태깅 쿨다운(방문함 N일 내)
> 영구·한시 부적합 > 수신거부.
상호 없음은 연락할 상호가 없는 사업장('업소명없음', 업종명이 상호로 들어간 행)이다. 적재는 그대로 두고 명부에서만 뺀다.
수신거부는 TAG_FEEDBACK의 '부적합·접촉 불가' 태깅에서만 파생된다. 은행 내부 동의관리 시스템의 고객 단위
데이터는 조회하지 않는다(RULE-SEC-01).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from backend.common.schemas.business import BusinessCandidate, TagHistoryEntry

OPT_OUT_REASON = "UNREACHABLE"  # 접촉 불가 = 수신거부 취급(RULE-TARGET-01 부록 C)

EXCLUSION_ORDER = ("OPERATING_STATUS", "INVALID_NAME", "CONTACT_COOLDOWN", "REJECTED", "OPT_OUT")


@dataclass(frozen=True)
class ExclusionParams:
    contact_cooldown_days: int
    # 부적합 사유별 배제 기간(일). 0 = 영구
    reject_exclusion_days: dict[str, int] = field(default_factory=dict)
    # 공백을 지운 상호가 이 값으로 시작하면 배제(예: '업소명없음')
    invalid_name_prefixes: tuple[str, ...] = ()
    # 상호가 업종 분류명 중 하나와 같으면 배제(예: '경영컨설팅업')
    exclude_industry_named: bool = False


def _compact(value: str | None) -> str:
    return "".join((value or "").split())


def has_invalid_name(candidate: BusinessCandidate, params: ExclusionParams) -> bool:
    """연락할 상호가 없는 사업장인지. 상가정보 상호는 '상호 지점명'이라 접두어로 비교한다."""
    name = _compact(candidate.name)
    if not name:
        return True
    if any(prefix and name.startswith(_compact(prefix)) for prefix in params.invalid_name_prefixes):
        return True
    if params.exclude_industry_named:
        industry_parts = {_compact(part) for part in candidate.industry_name.split("·")}
        if name in industry_parts:
            return True
    return False


def _is_recent(tagged_on: date, target_date: date, days: int) -> bool:
    return 0 <= (target_date - tagged_on).days < days


def exclusion_reason(
    candidate: BusinessCandidate,
    history: list[TagHistoryEntry],
    target_date: date,
    params: ExclusionParams,
) -> str | None:
    """배제 사유 코드(EXCLUSION_ORDER 중 가장 앞선 것). 통과면 None."""
    if candidate.operating_status != "정상":
        return "OPERATING_STATUS"

    if has_invalid_name(candidate, params):
        return "INVALID_NAME"

    if params.contact_cooldown_days > 0 and any(
        entry.tag_value == "VISITED" and _is_recent(entry.tagged_on, target_date, params.contact_cooldown_days)
        for entry in history
    ):
        return "CONTACT_COOLDOWN"

    rejected = [entry for entry in history if entry.tag_value == "REJECTED" and entry.reject_reason]
    for entry in rejected:
        if entry.reject_reason == OPT_OUT_REASON:
            continue
        days = params.reject_exclusion_days.get(entry.reject_reason or "", 0)
        if days == 0 or _is_recent(entry.tagged_on, target_date, days):
            return "REJECTED"

    for entry in rejected:
        if entry.reject_reason != OPT_OUT_REASON:
            continue
        days = params.reject_exclusion_days.get(OPT_OUT_REASON, 0)
        if days == 0 or _is_recent(entry.tagged_on, target_date, days):
            return "OPT_OUT"
    return None


def apply_exclusions(
    candidates: list[BusinessCandidate],
    tag_history: list[TagHistoryEntry],
    target_date: date,
    params: ExclusionParams,
) -> tuple[list[BusinessCandidate], dict[str, int]]:
    by_business: dict[int, list[TagHistoryEntry]] = defaultdict(list)
    for entry in tag_history:
        by_business[entry.business_id].append(entry)

    passed: list[BusinessCandidate] = []
    excluded: Counter[str] = Counter()
    for candidate in candidates:
        reason = exclusion_reason(candidate, by_business.get(candidate.id, []), target_date, params)
        if reason is None:
            passed.append(candidate)
        else:
            excluded[reason] += 1
    return passed, {reason: excluded.get(reason, 0) for reason in EXCLUSION_ORDER}
