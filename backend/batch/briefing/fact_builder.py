"""선정 사유 사실 문장 생성 (RULE-BRIEF-01) — 결정론적 템플릿, LLM 미사용.

사실 문장은 이벤트의 최신 신호(스냅샷 원본에서 정규화된 값)와 BUSINESS 공개 데이터로만 만든다.
모든 문장에 `소스명·기준일` 출처 태그가 붙는다. LLM은 이 문장을 바꾸거나 새로 만들지 않는다.

문장 구성: "관측된 사실(수치·기준일) + 영업 관점의 의미(왜 지금 연락할 만한지)".
- 의미 부분은 신호 종류별 고정 문구다(추정은 '~수 있습니다'로 표현). 새 수치를 만들지 않는다.
- 화법(LLM·정형)에 쓰는 연락 사유·목적(call_reason/call_purpose)도 여기서 함께 정한다.
- 상품·여신 용어(BriefingConfig.product_terms)는 쓰지 않는다 — 화법 단계에서 차단되기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from backend.common.config import PipelineConfig
from backend.common.schemas.brief import BriefFact
from backend.common.schemas.business import BusinessCandidate
from backend.common.schemas.event import ActiveEvent
from backend.common.schemas.recommendation import ScoredCandidate

# 모집단 사실 문장의 출처 — BUSINESS.status_source → 스냅샷 소스명
_POPULATION_SOURCE = {"PERMIT": "PERMIT_FULL", "SBIZ": "SBIZ_STORE", "NTS": "NTS_STATUS"}

# 신호가 없을 때(신선도 항만으로 선정)의 연락 사유·목적
_DEFAULT_CALL_REASON = "저희 지점 담당 상권에서 영업 중이신 사업장께 인사드리고자"
_DEFAULT_CALL_PURPOSE = "가까운 지점에서 사업장 운영에 필요하신 금융 업무를 편하게 보실 수 있도록 도와드리고자"


@dataclass(frozen=True)
class ReasonFact:
    fact: BriefFact
    summary: str  # 명부 카드용 1줄 요약 — "무엇이 바뀌었나 — 왜 연락하나"
    # 화법용: "{call_reason} 연락드렸습니다." / "{call_purpose} 합니다." 형태로 이어 쓴다
    call_reason: str = _DEFAULT_CALL_REASON
    call_purpose: str = _DEFAULT_CALL_PURPOSE


@dataclass(frozen=True)
class _Built:
    text: str
    summary: str
    call_reason: str
    call_purpose: str


def _tag(config: PipelineConfig, source_name: str, as_of: str) -> BriefFact:
    display = config.source_display_name(source_name)
    return BriefFact(text="", source_tag=f"{display}·{as_of}", source_name=display, as_of_date=as_of)


def _num(detail: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(detail.get(key, default))
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _event_fact(event: ActiveEvent) -> _Built | None:
    detail = event.detail or {}
    kind = event.signal_type
    if kind == "NEW_BUSINESS_OPENING":
        licensed_raw = detail.get("licensed_on") or event.as_of_date.isoformat()
        licensed = _parse_date(licensed_raw)
        elapsed = max(0, (event.as_of_date - licensed).days) if licensed else None
        elapsed_text = f"인허가 후 {elapsed}일 지난" if elapsed else "막 인허가를 받은"
        return _Built(
            text=(
                f"{licensed_raw}에 인허가를 받은 신규 개업 사업장입니다({elapsed_text} 시점). "
                "개업 초기에는 주거래 은행과 매출 정산 계좌를 새로 정하는 경우가 많아, "
                "첫 거래 관계를 만들기 좋은 시기입니다."
            ),
            summary="신규 개업 사업장 — 주거래 은행을 정하기 전, 첫 거래를 만들 적기",
            # '문을 여신'은 상품 용어 '여신'으로 차단되므로 '개업하신'으로 쓴다
            call_reason="최근 새로 개업하신 것을 확인하고 개업 인사차",
            call_purpose="개업 초기에 필요하신 매출 정산 계좌 개설이나 사업 운영 자금 준비를 지점에서 직접 도와드리고자",
        )
    if kind == "INDUSTRY_NEW_OPENINGS":
        count = int(_num(detail, "count", event.raw_value))
        industry = detail.get("industry_name") or event.industry_name or "동일 업종"
        radius = _num(detail, "radius_km")
        return _Built(
            text=(
                f"담당 상권 반경 {radius:g}km 안에 같은 업종({industry}) 매장이 최근 {count}곳 새로 생겼습니다. "
                "경쟁 매장이 늘면 매출 관리와 운영 자금 점검이 필요해지는 경우가 많아, "
                "기존 사업장에 먼저 연락드릴 이유가 됩니다."
            ),
            summary=f"같은 업종 경쟁 매장 {count}곳 신규 개업 — 매출·운영 자금 점검 수요",
            call_reason=f"최근 주변에 같은 업종 매장이 {count}곳 새로 문을 열어 상권 변화를 말씀드리고자",
            call_purpose="경쟁이 늘어나는 시기에 매출 관리나 운영 자금 흐름에서 불편하신 점이 없는지 여쭙고 도와드리고자",
        )
    if kind == "AREA_NEW_OPENINGS":
        count = int(_num(detail, "count", event.raw_value))
        radius = _num(detail, "radius_km")
        return _Built(
            text=(
                f"담당 상권 반경 {radius:g}km 안에서 최근 신규 개업이 {count}건 확인되었습니다. "
                "상권에 새 매장이 늘면 유동 고객과 결제 건수도 함께 변할 수 있어, "
                "주변 사업장의 운영 준비 상황을 확인해 볼 시점입니다."
            ),
            summary=f"인근 상권 신규 개업 {count}건 — 상권이 활발해지는 시기, 운영 준비 점검",
            call_reason=f"최근 주변 상권에 새로 문을 연 사업장이 {count}곳 늘어 지역 상권 소식을 전해 드리고자",
            call_purpose="상권이 바뀌는 시기에 사업장 운영에 필요하신 금융 업무를 지점에서 먼저 챙겨드리고자",
        )
    if kind == "FX_DAILY_CHANGE":
        rate = _num(detail, "rate")
        change = _num(detail, "change_pct")
        return _Built(
            text=(
                f"원/달러 환율이 {rate:,.2f}원으로 전일 대비 {change:+.2f}% 변동했습니다. "
                "수입 원가나 해외 결제·송금 비용이 달라질 수 있는 업종이라, "
                "환전·송금 시점 관리에 대한 상담 수요가 생길 수 있습니다."
            ),
            summary=f"환율 {change:+.2f}% 변동 — 해외 결제·송금 비용 부담 점검",
            call_reason="최근 원/달러 환율 변동이 커져 해외 거래가 있는 사업장에 상황을 여쭙고자",
            call_purpose="수입 대금 결제나 해외 송금, 환전 시점 관리에서 부담되시는 부분을 확인하고 도와드리고자",
        )
    if kind == "OIL_PRICE_CHANGE":
        sido = detail.get("sido") or "지역"
        change = _num(detail, "change_pct")
        return _Built(
            text=(
                f"{sido} 평균 휘발유 가격이 전일 대비 {change:+.2f}% 변동했습니다. "
                "연료비 비중이 큰 업종이라 운영비와 자금 흐름에 바로 영향을 받을 수 있어, "
                "자금 운용 상황을 함께 점검해 볼 시점입니다."
            ),
            summary=f"{sido} 유가 {change:+.2f}% 변동 — 연료비·운영 자금 부담 변화",
            call_reason="최근 지역 유가가 움직여 연료비 부담이 달라지셨을 것 같아",
            call_purpose="운영비 변화에 따른 자금 흐름 관리에서 필요하신 부분을 미리 여쭙고 도와드리고자",
        )
    if kind == "WEATHER_WARNING":
        warning = detail.get("warning") or "기상특보"
        sido = detail.get("sido") or "지점 소재지"
        return _Built(
            text=(
                f"{sido} 관할에 {warning}가 발효되었습니다. "
                "날씨 영향을 받는 업종이라 영업 차질이나 일시적인 매출 변동이 생길 수 있어, "
                "안부 연락으로 관계를 만들기 좋은 시점입니다."
            ),
            summary=f"{warning} 발효 — 영업 차질 우려, 안부 연락 적기",
            call_reason=f"{warning}가 발효되어 영업에 지장은 없으신지 안부를 여쭙고자",
            call_purpose="날씨 때문에 매출이 흔들릴 때 필요하실 수 있는 자금 운용 지원을 지점에서 안내해 드리고자",
        )
    return None


def _population_fact(candidate: BusinessCandidate) -> tuple[str, str]:
    industry = candidate.industry_name or "업종 미상"
    text = (
        f"지점에서 약 {candidate.distance_km:.1f}km 거리에서 영업 중인 {industry} 사업장으로, "
        "직접 방문 상담이 쉬운 담당 상권 안에 있습니다."
    )
    return text, "담당 상권 내 영업 중 사업장 — 방문 상담이 쉬운 거리"


def _license_age_fact(licensed_on: date, as_of: date) -> tuple[str, str]:
    years = max(0, (as_of - licensed_on).days) // 365
    if years < 1:
        return (
            f"{licensed_on.isoformat()}에 인허가를 받은 개업 1년 미만 사업장으로, "
            "거래 은행 등 사업 초기 금융 관계를 정비하는 시기입니다.",
            "개업 1년 미만 — 사업 초기 금융 관계 정비 시기",
        )
    return (
        f"{licensed_on.isoformat()}에 인허가를 받아 {years}년째 영업 중인 사업장으로, "
        "영업 기반이 자리 잡은 안정 운영 단계입니다.",
        f"{years}년째 영업 중 — 안정 운영 단계",
    )


def build_reason_facts(
    candidate: BusinessCandidate,
    scored: ScoredCandidate,
    events_by_id: dict[int, ActiveEvent],
    config: PipelineConfig,
    *,
    max_event_facts: int = 3,
) -> list[ReasonFact]:
    """기여도 높은 이벤트 순으로 사실 문장을 만들고, 마지막에 모집단(공개 데이터) 사실을 붙인다.

    첫 문장(가장 기여도 높은 사유)의 call_reason/call_purpose가 화법의 연락 사유·목적이 된다.
    """
    facts: list[ReasonFact] = []
    seen_types: set[str] = set()
    for contribution in scored.contributions:
        if len(facts) >= max_event_facts:
            break
        event = events_by_id.get(contribution.event_id)
        if event is None or event.signal_type in seen_types:
            continue
        built = _event_fact(event)
        if built is None:
            continue
        seen_types.add(event.signal_type)
        tag = _tag(config, event.source_name, event.as_of_date.isoformat())
        facts.append(
            ReasonFact(
                fact=tag.model_copy(update={"text": built.text}),
                summary=built.summary,
                call_reason=built.call_reason,
                call_purpose=built.call_purpose,
            )
        )

    population_source = _POPULATION_SOURCE.get(candidate.status_source, "SBIZ_STORE")
    as_of = candidate.population_as_of.isoformat()
    population_text, population_summary = _population_fact(candidate)
    facts.append(
        ReasonFact(
            fact=_tag(config, population_source, as_of).model_copy(update={"text": population_text}),
            summary=population_summary,
        )
    )
    if candidate.licensed_on is not None and "NEW_BUSINESS_OPENING" not in seen_types:
        text, summary = _license_age_fact(candidate.licensed_on, candidate.population_as_of)
        facts.append(
            ReasonFact(
                fact=_tag(config, "PERMIT_FULL", as_of).model_copy(update={"text": text}),
                summary=summary,
            )
        )
    return facts
