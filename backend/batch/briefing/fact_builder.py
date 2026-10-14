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


def _event_fact(event: ActiveEvent, reference_date: date | None = None) -> _Built | None:
    """reference_date: 명부 생성일. 경과일은 이 날짜 기준으로 센다(없으면 이벤트 기준일).

    이벤트는 활성 기간 동안 여러 날 명부에 재사용되므로, 이벤트 기준일로 세면
    며칠 뒤 명부에서도 '인허가 후 1일'처럼 오래된 경과일이 표시된다.
    """
    detail = event.detail or {}
    kind = event.signal_type
    if kind == "NEW_BUSINESS_OPENING":
        licensed_raw = detail.get("licensed_on") or event.as_of_date.isoformat()
        licensed = _parse_date(licensed_raw)
        base_date = reference_date or event.as_of_date
        elapsed = max(0, (base_date - licensed).days) if licensed else None
        elapsed_text = f"인허가 후 {elapsed}일 지난" if elapsed else "막 인허가를 받은"
        if licensed is None:
            summary_head = "신규 개업 사업장"
        elif elapsed:
            summary_head = f"{_md(licensed)} 인허가, 개업 {elapsed}일째"
        else:
            summary_head = f"{_md(licensed)} 인허가, 개업 당일"
        return _Built(
            text=(
                f"{licensed_raw}에 인허가를 받은 신규 개업 사업장입니다({elapsed_text} 시점). "
                "개업 초기에는 주거래 은행과 매출 정산 계좌를 새로 정하는 경우가 많아, "
                "첫 거래 관계를 만들기 좋은 시기입니다."
            ),
            summary=f"{summary_head} — 첫 거래를 만들 적기",
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
                # 신규 개업 사업장에도 붙을 수 있으므로 '기존 사업장' 같은 표현을 쓰지 않는다(10/13 수정 요청 ②-3).
                "경쟁 매장이 늘면 매출 흐름이 달라지는 경우가 많아, "
                "운영 자금 점검이 필요해질 수 있는 시기입니다."
            ),
            summary=(
                f"{_radius_text(radius)}같은 업종 {count}곳 신규 개업 ({_mmdd(event.as_of_date)} 기준) "
                "— 매출·운영 자금 점검 수요"
            ),
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
            summary=(
                f"{_radius_text(radius)}신규 개업 {count}건 ({_mmdd(event.as_of_date)} 기준) "
                "— 상권 변화, 운영 준비 점검"
            ),
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
            summary=f"원/달러 {change:+.2f}% ({_mmdd(event.as_of_date)} 기준) — 해외 결제·송금 비용 부담 점검",
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
            summary=f"{sido} 휘발유 {change:+.2f}% ({_mmdd(event.as_of_date)} 기준) — 연료비·운영 자금 부담 변화",
            call_reason="최근 지역 유가가 움직여 연료비 부담이 달라지셨을 것 같아",
            call_purpose="운영비 변화에 따른 자금 흐름 관리에서 필요하신 부분을 미리 여쭙고 도와드리고자",
        )
    if kind in _FORECAST_KINDS:
        return _forecast_fact(kind, detail)
    if kind == "WEATHER_WARNING":
        warning = detail.get("warning") or "기상특보"
        sido = detail.get("sido") or "지점 소재지"
        return _Built(
            text=(
                f"{sido} 관할에 {warning}가 발효되었습니다. "
                "날씨 영향을 받는 업종이라 영업 차질이나 일시적인 매출 변동이 생길 수 있어, "
                "안부 연락으로 관계를 만들기 좋은 시점입니다."
            ),
            summary=(
                f"{detail.get('sido') + ' ' if detail.get('sido') else ''}{warning} 발효 "
                f"({_mmdd(event.as_of_date)} 기준) — 영업 차질 우려, 안부 연락 적기"
            ),
            call_reason=f"{warning}가 발효되어 영업에 지장은 없으신지 안부를 여쭙고자",
            call_purpose="날씨 때문에 매출이 흔들릴 때 필요하실 수 있는 자금 운용 지원을 지점에서 안내해 드리고자",
        )
    return None


_FORECAST_KINDS = frozenset(
    {"TEMP_SHIFT_FORECAST", "SEASON_SHIFT_FORECAST", "FIRST_FREEZE_FORECAST", "FIRST_HEAT_FORECAST"}
)
# 예보 사유의 화법 목적 — 상품·여신 용어 없이 운영 준비를 돕는다는 수준으로만 말한다.
_FORECAST_CALL_PURPOSE = "계절이 바뀌는 시기에 필요하신 운영 자금 흐름이나 결제 관련 업무를 지점에서 미리 챙겨드리고자"


def _mmdd(value: Any) -> str:
    """명부 1줄 요약용 기준일 표기 — 2026-10-09 → 10.09"""
    parsed = value if isinstance(value, date) else _parse_date(value)
    return f"{parsed.month:02d}.{parsed.day:02d}" if parsed else str(value)


def _date_prefix(value: Any) -> str:
    """예보 대상일이 있을 때만 '10.15 ' 접두어를 붙인다."""
    return f"{_mmdd(value)} " if _parse_date(value) else ""


def _radius_text(radius: float) -> str:
    """반경 값이 있을 때만 '반경 1km ' 접두어를 붙인다(데이터에 없는 값은 만들지 않음)."""
    return f"반경 {radius:g}km " if radius > 0 else ""


def _md(iso: Any) -> str:
    parsed = _parse_date(iso)
    return f"{parsed.month}월 {parsed.day}일" if parsed else str(iso)


def _deg(value: Any) -> str:
    try:
        return f"{float(value):g}°C"
    except (TypeError, ValueError):
        return f"{value}°C"


def _forecast_fact(kind: str, detail: dict[str, Any]) -> _Built:
    """예보 사실 문장 — 발표 시각과 '예보'를 반드시 밝힌다(단정하지 않음)."""
    issued = detail.get("issued") or "최근 발표"
    if kind == "TEMP_SHIFT_FORECAST":
        diff = float(detail.get("diff") or 0)
        direction = "낮을" if diff < 0 else "높을"
        word = "하락" if diff < 0 else "상승"
        return _Built(
            text=(
                f"기상청 단기예보({issued})에 따르면 {_md(detail.get('forecast_date'))} "
                f"{detail.get('kind', '최저')}기온이 {_deg(detail.get('forecast_value'))}로 "
                f"오늘({_deg(detail.get('today_value'))})보다 {abs(diff):g}°C {direction} 것으로 예보되었습니다. "
                "기온이 크게 바뀌는 시기에는 계절 물품 준비나 영업 방식에 변화가 생기기 쉬워, "
                "미리 안부를 여쭙기 좋은 시점입니다."
            ),
            summary=f"{_date_prefix(detail.get('forecast_date'))}기온 {abs(diff):g}°C {word} 예보 — 계절 준비 수요 점검",
            call_reason=f"기온이 크게 {'내려갈' if diff < 0 else '올라갈'} 것으로 예보되어 영업 준비에 불편은 없으신지 여쭙고자",
            call_purpose=_FORECAST_CALL_PURPOSE,
        )
    if kind == "SEASON_SHIFT_FORECAST":
        diff = float(detail.get("diff") or 0)
        direction = "낮을" if diff < 0 else "높을"
        word = "추워지는" if diff < 0 else "더워지는"
        return _Built(
            text=(
                f"기상청 중기예보({detail.get('issued_mid') or issued})에 따르면 "
                f"{_md(detail.get('far_start'))}~{_md(detail.get('far_end'))} 평균 최저기온이 "
                f"{_deg(detail.get('far_mean'))}로, {_md(detail.get('near_start'))}~{_md(detail.get('near_end'))} "
                f"평균({_deg(detail.get('near_mean'))})보다 {abs(diff):g}°C {direction} 것으로 예보되었습니다. "
                "계절이 바뀌는 시기라 판매 품목 교체나 냉난방 준비 같은 운영 변화가 생기기 쉽습니다."
            ),
            summary=(
                f"{_date_prefix(detail.get('far_start'))}계절 전환 예보"
                f"(평균 최저 {abs(diff):g}°C {'하락' if diff < 0 else '상승'}) — 계절 운영 준비 시기"
            ),
            call_reason=f"날씨가 {word} 시기로 접어든다는 예보가 있어 계절 준비 상황을 여쭙고자",
            call_purpose=_FORECAST_CALL_PURPOSE,
        )
    if kind == "FIRST_FREEZE_FORECAST":
        day = _parse_date(detail.get("forecast_date"))
        season_word = "올겨울" if day and day.month in (12, 1, 2) else "올가을"
        origin = "중기예보" if detail.get("origin") == "중기" else "단기예보"
        return _Built(
            text=(
                f"기상청 {origin}({issued})에 따르면 {_md(detail.get('forecast_date'))} 최저기온이 "
                f"{_deg(detail.get('value'))}로, {season_word} 들어 처음 영하가 예보되었습니다. "
                "난방 준비와 겨울철 운영 전환이 시작되는 시점입니다."
            ),
            summary=(
                f"{_date_prefix(detail.get('forecast_date'))}{season_word} 첫 영하 예보"
                f"({_deg(detail.get('value'))}) — 겨울철 운영 준비 시기"
            ),
            call_reason=f"{season_word} 첫 영하 날씨가 예보되어 겨울철 준비에 불편은 없으신지 여쭙고자",
            call_purpose=_FORECAST_CALL_PURPOSE,
        )
    # FIRST_HEAT_FORECAST
    origin = "중기예보" if detail.get("origin") == "중기" else "단기예보"
    return _Built(
        text=(
            f"기상청 {origin}({issued})에 따르면 {_md(detail.get('forecast_date'))} 최고기온이 "
            f"{_deg(detail.get('value'))}로, 올해 처음 폭염 수준(33°C 이상)이 예보되었습니다. "
            "냉방·음료 수요가 커지는 시기라 여름철 운영 준비를 점검해 볼 시점입니다."
        ),
        summary=(
            f"{_date_prefix(detail.get('forecast_date'))}올해 첫 폭염 예보"
            f"({_deg(detail.get('value'))}) — 여름철 운영 준비 시기"
        ),
        call_reason="올해 첫 폭염 수준의 더위가 예보되어 여름철 준비에 불편은 없으신지 여쭙고자",
        call_purpose=_FORECAST_CALL_PURPOSE,
    )


def _population_fact(candidate: BusinessCandidate) -> tuple[str, str]:
    industry = candidate.industry_name or "업종 미상"
    text = (
        f"지점에서 약 {candidate.distance_km:.1f}km 거리에서 영업 중인 {industry} 사업장으로, "
        "직접 방문 상담이 쉬운 담당 상권 안에 있습니다."
    )
    # 명부 1줄 요약 — 신호 없이 선정된 행이 같은 문장으로 줄줄이 반복되지 않게 거리·업종(마지막 단계)을 넣는다.
    leaf = _industry_leaf(candidate.industry_name)
    subject = f"{leaf} 영업 중" if leaf else "영업 중 사업장"
    return text, f"지점에서 약 {candidate.distance_km:.1f}km, {subject} — 방문 상담이 쉬운 거리"


def _with_place(summary: str, candidate: BusinessCandidate) -> str:
    """'반경 1km 신규 개업 4건 (10.09 기준) — 상권 변화…' → '… (10.09 기준) · 한식 0.3km — 상권 변화…'"""
    leaf = _industry_leaf(candidate.industry_name)
    place = f"{leaf} {candidate.distance_km:.1f}km" if leaf else f"지점에서 {candidate.distance_km:.1f}km"
    head, sep, tail = summary.partition(" — ")
    return f"{head} · {place}{sep}{tail}"


def _industry_leaf(industry: str | None) -> str:
    """'시설관리·임대·여행사·보조·여행사' → '여행사' (화면 표시와 같은 규칙)"""
    parts = [part.strip() for part in (industry or "").split("·") if part.strip()]
    return parts[-1] if parts else ""


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
    reference_date: date | None = None,
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
        built = _event_fact(event, reference_date)
        if built is None:
            continue
        seen_types.add(event.signal_type)
        tag = _tag(config, event.source_name, event.as_of_date.isoformat())
        # 상권·업종 단위 신호는 같은 이벤트가 여러 행에 붙어 요약이 똑같아진다 — 사업장의 업종·거리를 덧붙인다.
        summary = built.summary if event.scope == "BUSINESS" else _with_place(built.summary, candidate)
        facts.append(
            ReasonFact(
                fact=tag.model_copy(update={"text": built.text}),
                summary=summary,
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
