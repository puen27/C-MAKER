"""선정 사유 사실 문장 생성 (RULE-BRIEF-01) — 결정론적 템플릿, LLM 미사용.

사실 문장은 이벤트의 최신 신호(스냅샷 원본에서 정규화된 값)와 BUSINESS 공개 데이터로만 만든다.
모든 문장에 `소스명·기준일` 출처 태그가 붙는다. LLM은 이 문장을 바꾸거나 새로 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.common.config import PipelineConfig
from backend.common.schemas.brief import BriefFact
from backend.common.schemas.business import BusinessCandidate
from backend.common.schemas.event import ActiveEvent
from backend.common.schemas.recommendation import ScoredCandidate

# 모집단 사실 문장의 출처 — BUSINESS.status_source → 스냅샷 소스명
_POPULATION_SOURCE = {"PERMIT": "PERMIT_FULL", "SBIZ": "SBIZ_STORE", "NTS": "NTS_STATUS"}


@dataclass(frozen=True)
class ReasonFact:
    fact: BriefFact
    summary: str  # 명부 카드용 1줄 요약


def _tag(config: PipelineConfig, source_name: str, as_of: str) -> BriefFact:
    display = config.source_display_name(source_name)
    return BriefFact(text="", source_tag=f"{display}·{as_of}", source_name=display, as_of_date=as_of)


def _num(detail: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(detail.get(key, default))
    except (TypeError, ValueError):
        return default


def _event_fact(event: ActiveEvent, config: PipelineConfig) -> tuple[str, str] | None:
    detail = event.detail or {}
    kind = event.signal_type
    if kind == "NEW_BUSINESS_OPENING":
        licensed = detail.get("licensed_on") or event.as_of_date.isoformat()
        return f"{licensed} 인허가된 신규 개업 사업장입니다.", f"신규 개업 사업장(인허가 {licensed})"
    if kind == "INDUSTRY_NEW_OPENINGS":
        count = int(_num(detail, "count", event.raw_value))
        industry = detail.get("industry_name") or event.industry_name or "동일 업종"
        radius = _num(detail, "radius_km")
        return (
            f"담당 상권 반경 {radius:g}km에서 같은 업종({industry}) 신규 개업이 {count}건 확인되었습니다.",
            f"상권 내 동일 업종 신규 개업 {count}건",
        )
    if kind == "AREA_NEW_OPENINGS":
        count = int(_num(detail, "count", event.raw_value))
        radius = _num(detail, "radius_km")
        return (
            f"담당 상권 반경 {radius:g}km에서 신규 개업이 {count}건 감지되었습니다.",
            f"인근 상권 신규 개업 {count}건 감지",
        )
    if kind == "FX_DAILY_CHANGE":
        rate = _num(detail, "rate")
        change = _num(detail, "change_pct")
        return (
            f"원/달러 환율이 {rate:,.2f}원으로 전일 대비 {change:+.2f}% 변동했습니다.",
            f"원/달러 환율 {change:+.2f}% 변동",
        )
    if kind == "OIL_PRICE_CHANGE":
        sido = detail.get("sido") or "지역"
        change = _num(detail, "change_pct")
        return (
            f"{sido} 평균 휘발유 가격이 전일 대비 {change:+.2f}% 변동했습니다.",
            f"{sido} 유가 {change:+.2f}% 변동",
        )
    if kind == "WEATHER_WARNING":
        warning = detail.get("warning") or "기상특보"
        sido = detail.get("sido") or "지점 소재지"
        return f"{sido} 관할 기상특보로 {warning}가 발효되었습니다.", f"{warning} 발효"
    return None


def build_reason_facts(
    candidate: BusinessCandidate,
    scored: ScoredCandidate,
    events_by_id: dict[int, ActiveEvent],
    config: PipelineConfig,
    *,
    max_event_facts: int = 3,
) -> list[ReasonFact]:
    """기여도 높은 이벤트 순으로 사실 문장을 만들고, 마지막에 모집단(공개 데이터) 사실을 붙인다."""
    facts: list[ReasonFact] = []
    seen_types: set[str] = set()
    for contribution in scored.contributions:
        if len(facts) >= max_event_facts:
            break
        event = events_by_id.get(contribution.event_id)
        if event is None or event.signal_type in seen_types:
            continue
        built = _event_fact(event, config)
        if built is None:
            continue
        seen_types.add(event.signal_type)
        text, summary = built
        tag = _tag(config, event.source_name, event.as_of_date.isoformat())
        facts.append(ReasonFact(fact=tag.model_copy(update={"text": text}), summary=summary))

    population_source = _POPULATION_SOURCE.get(candidate.status_source, "SBIZ_STORE")
    as_of = candidate.population_as_of.isoformat()
    industry = candidate.industry_name or "업종 미상"
    population_text = f"담당 상권(지점에서 약 {candidate.distance_km:.1f}km) 내 영업 중인 {industry} 사업장입니다."
    facts.append(
        ReasonFact(
            fact=_tag(config, population_source, as_of).model_copy(update={"text": population_text}),
            summary="담당 상권 내 영업 중 사업장",
        )
    )
    if candidate.licensed_on is not None and "NEW_BUSINESS_OPENING" not in seen_types:
        text = f"인허가일자는 {candidate.licensed_on.isoformat()}입니다."
        facts.append(
            ReasonFact(fact=_tag(config, "PERMIT_FULL", as_of).model_copy(update={"text": text}),
                       summary=f"인허가 {candidate.licensed_on.isoformat()}")
        )
    return facts
