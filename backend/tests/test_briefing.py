"""TEST-03: 브리프 그라운딩 회귀 테스트셋 (RULE-BRIEF-01~03).

LLM 출력 예시를 고정해 두고, 근거 없는 수치·금칙 표현·상품 안내가 차단되는지 확인한다.
실제 게이트웨이를 호출하지 않는다(가짜 LLM 클라이언트).
"""

from __future__ import annotations

import json

import pytest

from backend.batch.briefing.brief_generator import generate_brief, parse_script
from backend.batch.briefing.citation_guard import validate_facts, validate_script
from backend.batch.briefing.fact_builder import build_reason_facts
from backend.batch.briefing.llm_client import LlmResult, LlmUnavailableError
from backend.batch.targeting.scorer import WeightTable, score_candidate
from backend.common.config import get_pipeline_config
from backend.common.schemas.brief import BriefFact, BriefInput
from backend.tests.factories import TODAY, active_event, branch, candidate, fact, weights

CONFIG = get_pipeline_config()
BRIEFING = CONFIG.briefing
FACTS = [
    fact("담당 상권 반경 1.5km에서 신규 개업이 5건 감지되었습니다."),
    fact("원/달러 환율이 1,382.50원으로 전일 대비 +1.25% 변동했습니다.", "한국은행ECOS", "2026-09-28"),
]
CONTEXT = ["강남중앙지점", "예시상점01", BRIEFING.greeting_org_name]


# 회귀 테스트셋: (LLM이 쓴 문장, 통과 여부)
REGRESSION_SET = [
    ("안녕하세요, ○○은행 강남중앙지점입니다.", True),
    ("최근 담당 상권에서 신규 개업이 5건 감지되어 인사드립니다.", True),
    ("환율이 전일 대비 1.25% 변동해 여쭤보고자 연락드렸습니다.", True),
    ("최근 상권에 신규 개업이 12건이나 늘었습니다.", False),          # 근거 없는 수치
    ("매출이 30% 증가할 것으로 보입니다.", False),                    # 근거 없는 수치
    ("2026년 10월 1일부터 혜택이 시작됩니다.", False),                # 근거 없는 날짜
    ("확정 수익을 드리는 상품이 있습니다.", False),                   # 금칙 표현
    ("원금보장 상품을 소개해 드리겠습니다.", False),                  # 금칙 표현
    ("사업자 대출 한도를 안내해 드릴 수 있습니다.", False),           # 상품 안내(상품설명서 인용 없음)
    ("금리 우대 적금을 소개드리고 싶습니다.", False),                 # 상품 안내
    ("[지방행정인허가·2026-09-27] 잠시 방문드려도 될까요?", True),     # 출처 태그는 제거 후 통과
]


@pytest.mark.parametrize(("sentence", "should_pass"), REGRESSION_SET)
def test_grounding_regression_set(sentence, should_pass):
    kept, errors = validate_script([sentence], FACTS, BRIEFING, allowed_context=CONTEXT)
    assert bool(kept) is should_pass, errors


def test_script_is_limited_to_three_sentences():
    lines = ["안녕하세요.", "인사드립니다.", "방문드려도 될까요?", "감사합니다."]
    kept, errors = validate_script(lines, FACTS, BRIEFING)
    assert len(kept) == 3
    assert any("절삭" in e for e in errors)


def test_facts_without_source_tag_are_removed():
    facts = [
        fact("정상 문장입니다."),
        BriefFact(text="태그 없는 문장입니다.", source_tag="", source_name="", as_of_date=""),
        BriefFact(text="잘못된 태그", source_tag="지방행정인허가 2026/09/27", source_name="x", as_of_date="x"),
    ]
    kept, errors = validate_facts(facts, BRIEFING)
    assert [f.text for f in kept] == ["정상 문장입니다."]
    assert len(errors) == 2


def test_parse_script_accepts_json_and_plain_text():
    assert parse_script('설명 {"script": ["가.", "나."]} 끝') == ["가.", "나."]
    assert parse_script("첫 줄\n둘째 줄") == ["첫 줄", "둘째 줄"]


class FakeLlm:
    def __init__(self, text: str | None = None, error: bool = False) -> None:
        self.text = text
        self.error = error
        self.model = "fake-model"

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int) -> LlmResult:
        payload = json.loads(user_prompt)
        assert payload["facts"] == [f.text for f in FACTS]  # LLM 입력은 확정 사실 문장뿐
        if self.error:
            raise LlmUnavailableError("timeout")
        return LlmResult(text=self.text or "", model=self.model)


def _input() -> BriefInput:
    return BriefInput(recommendation_id=1, branch_name="강남중앙지점", business_name="예시상점01",
                      industry_name="음식·한식", distance_km=0.5, facts=FACTS)


def test_generate_brief_with_llm_keeps_only_grounded_sentences():
    llm = FakeLlm(json.dumps({"script": [
        "안녕하세요, ○○은행 강남중앙지점입니다.", "매출이 30% 늘었습니다.", "잠시 방문드려도 될까요?"]},
        ensure_ascii=False))
    brief = generate_brief(_input(), reason_summary="요약", llm=llm, config=BRIEFING)  # type: ignore[arg-type]
    assert brief.generation_status == "LLM"
    assert brief.talk_script == ["안녕하세요, ○○은행 강남중앙지점입니다.", "잠시 방문드려도 될까요?"]
    assert brief.model_version == "fake-model" and brief.prompt and brief.raw_output


def test_generate_brief_blocks_everything_then_reason_only():
    llm = FakeLlm(json.dumps({"script": ["원금 보장 상품이 있습니다.", "대출 한도를 올려드립니다."]}, ensure_ascii=False))
    brief = generate_brief(_input(), reason_summary="요약", llm=llm, config=BRIEFING)  # type: ignore[arg-type]
    assert brief.generation_status == "REASON_ONLY"
    assert brief.talk_script == []
    assert brief.reason_facts == FACTS  # 사유는 그대로 표시


def test_generate_brief_falls_back_to_template_when_llm_unavailable():
    brief = generate_brief(_input(), reason_summary="요약", llm=FakeLlm(error=True), config=BRIEFING)  # type: ignore[arg-type]
    assert brief.generation_status == "TEMPLATE"
    assert 1 <= len(brief.talk_script) <= 3
    assert any("LLM 호출 실패" in e for e in brief.validation_errors)


def test_generate_brief_without_llm_uses_template():
    brief = generate_brief(_input(), reason_summary="요약", llm=None, config=BRIEFING)
    assert brief.generation_status == "TEMPLATE"
    assert brief.prompt is None and brief.model_version is None


def test_reason_facts_all_have_source_tags():
    events = [
        active_event(10, signal_type="NEW_BUSINESS_OPENING", scope="BUSINESS", target_key="BUSINESS:1",
                     business_id=1, intensity=0.9, detail={"licensed_on": "2026-09-25"}),
        active_event(11, signal_type="WEATHER_WARNING", scope="AREA", target_key="WEATHER:폭염주의보",
                     source_name="KMA_WARNING", detail={"warning": "폭염주의보", "sido": "서울"}),
    ]
    item = candidate(1, licensed_on=TODAY)
    table = WeightTable(weights(("NEW_BUSINESS_OPENING", "*", 1.5, 0), ("WEATHER_WARNING", "*", 0.5, 0)),
                        default_weight=1.0, min_sample=30)
    scored = score_candidate(branch(), item, events, table, None, TODAY, CONFIG)
    facts = build_reason_facts(item, scored, {e.event_id: e for e in events}, CONFIG)
    assert facts[0].fact.text.startswith("2026-09-25 인허가된 신규 개업")
    assert facts[0].fact.source_tag == "지방행정인허가·2026-09-29"
    kept, errors = validate_facts([f.fact for f in facts], BRIEFING)
    assert len(kept) == len(facts) and not errors
