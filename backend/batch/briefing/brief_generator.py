"""상담 브리프 생성 (REQ-06, RULE-BRIEF-01~03).

- 선정 사유(사실 문장·출처 태그)와 체크리스트는 결정론적으로 만든다(fact_builder).
- LLM은 확정된 사실 문장만 입력으로 받아 전화 화법(3문장 이내)만 쓴다. 순위·배제에 관여하지 않는다(CLAUDE.md §0.2).
- 화법은 citation_guard로 검증하고, 전부 차단되면 사유만 표시한다(REASON_ONLY, RULE-BRIEF-02).
- 게이트웨이 미설정·장애 시에는 사실을 담지 않은 정형 인사 화법으로 대체한다(TEMPLATE).
- 프롬프트·모델 버전·원문 출력을 함께 반환해 감사 추적에 보존한다(CLAUDE.md §6).
"""

from __future__ import annotations

import json
import re
import time

from backend.batch.briefing.citation_guard import validate_facts, validate_script
from backend.batch.briefing.llm_client import LlmClient, LlmUnavailableError
from backend.common.config import BriefingConfig
from backend.common.schemas.brief import BriefContent, BriefInput

PROMPT_VERSION = "brief-v1"

SYSTEM_PROMPT = """너는 은행 영업점 직원이 사업장에 처음 전화할 때 쓸 인사 화법 초안을 쓰는 도우미다.
규칙:
1. 사용자 메시지의 facts에 있는 내용만 언급할 수 있다. facts에 없는 사실·수치·날짜·혜택을 만들지 마라.
2. 금융상품·대출·금리·한도·수익을 안내하거나 권유하지 마라. '확정 수익', '원금 보장' 같은 표현을 쓰지 마라.
3. 개인에 대한 정보를 추측하거나 언급하지 마라.
4. 존댓말로 최대 3문장. 출처 태그나 대괄호는 쓰지 마라.
5. 출력은 JSON 한 개만: {"script": ["문장1", "문장2", "문장3"]}"""


def build_user_prompt(brief_input: BriefInput, config: BriefingConfig) -> str:
    return json.dumps(
        {
            "org_name": config.greeting_org_name,
            "branch_name": brief_input.branch_name,
            "business_name": brief_input.business_name,
            "industry": brief_input.industry_name,
            "facts": [fact.text for fact in brief_input.facts],
        },
        ensure_ascii=False,
    )


def template_script(brief_input: BriefInput, config: BriefingConfig) -> list[str]:
    """사실을 담지 않는 정형 화법(LLM 미가용 시). 지점명·상호 외의 정보를 넣지 않는다."""
    return [
        f"안녕하세요, {config.greeting_org_name} {brief_input.branch_name}입니다.",
        f"{brief_input.business_name} 주변 상권에서 최근 확인된 변화와 관련해 인사드리고자 연락드렸습니다.",
        "편하신 시간에 잠시 방문드려 필요하신 부분을 여쭤봐도 괜찮을까요?",
    ]


def parse_script(raw: str) -> list[str]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            script = data.get("script") if isinstance(data, dict) else None
            if isinstance(script, list):
                return [str(line) for line in script if str(line).strip()]
            if isinstance(script, str):
                return [script]
        except json.JSONDecodeError:
            pass
    return [line for line in raw.splitlines() if line.strip()]


def generate_brief(
    brief_input: BriefInput,
    *,
    reason_summary: str,
    llm: LlmClient | None,
    config: BriefingConfig,
) -> BriefContent:
    facts, errors = validate_facts(brief_input.facts, config)
    allowed_context = [brief_input.branch_name, brief_input.business_name, config.greeting_org_name]
    checklist = list(config.default_checklist)
    user_prompt = build_user_prompt(brief_input.model_copy(update={"facts": facts}), config)
    prompt_record = f"[{PROMPT_VERSION}]\n[system]\n{SYSTEM_PROMPT}\n[user]\n{user_prompt}"

    if llm is not None:
        started = time.monotonic()
        try:
            result = llm.complete(SYSTEM_PROMPT, user_prompt, max_tokens=config.max_output_tokens)
            latency_ms = int((time.monotonic() - started) * 1000)
            script, script_errors = validate_script(
                parse_script(result.text), facts, config, allowed_context=allowed_context
            )
            errors.extend(script_errors)
            return BriefContent(
                recommendation_id=brief_input.recommendation_id,
                reason_summary=reason_summary,
                reason_facts=facts,
                talk_script=script,
                checklist=checklist,
                generation_status="LLM" if script else "REASON_ONLY",
                validation_errors=errors,
                prompt=prompt_record,
                model_version=result.model,
                raw_output=result.text,
                latency_ms=latency_ms,
            )
        except LlmUnavailableError as exc:
            errors.append(f"LLM 호출 실패 — 정형 화법으로 대체: {exc}"[:300])

    script, script_errors = validate_script(
        template_script(brief_input, config), facts, config, allowed_context=allowed_context
    )
    errors.extend(script_errors)
    return BriefContent(
        recommendation_id=brief_input.recommendation_id,
        reason_summary=reason_summary,
        reason_facts=facts,
        talk_script=script,
        checklist=checklist,
        generation_status="TEMPLATE" if script else "REASON_ONLY",
        validation_errors=errors,
        prompt=prompt_record if llm is not None else None,
        model_version=None,
        raw_output=None,
        latency_ms=None,
    )
