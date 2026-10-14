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
from backend.batch.briefing.fact_builder import _industry_leaf
from backend.batch.briefing.llm_client import LlmClient, LlmUnavailableError
from backend.common.config import BriefingConfig
from backend.common.schemas.brief import BriefContent, BriefInput

PROMPT_VERSION = "brief-v6"

# call_reason/call_purpose가 비어 있을 때(구 입력·테스트)의 기본값 — 전화 말투(10/14 테스트 결과 10번)
# 차단 단어(카드·통장·상품·가입·혜택 등 product_terms)는 넣지 않는다.
_FALLBACK_CALL_REASON = "가까운 곳에서 영업하고 계셔서 인사드리려고"
_FALLBACK_CALL_PURPOSE = "필요하신 금융 업무를 가까운 지점에서 편하게 보실 수 있게 도와드리려고"
_CALL_ASK = "편하신 시간 알려주시면 제가 잠깐 찾아뵙고 인사드려도 될까요?"

SYSTEM_PROMPT = """너는 은행 영업점 직원이 사업장 사장님께 처음 전화할 때 읽을 화법 초안을 쓰는 도우미다.
사장님이 '왜 전화했는지, 나에게 무슨 도움이 되는지'를 바로 알 수 있게, 전화로 말하듯 자연스럽게 3문장으로 쓴다.
  1문장(인사·연락 사유): org_name·branch_name을 밝히고 call_reason으로 왜 지금 연락했는지 말한다.
  2문장(연락 목적): call_purpose를 바탕으로 지점이 무엇을 도와드리려는지 사장님 입장에서 말한다.
  3문장(다음 행동 요청): 편하신 시간에 직원이 찾아뵙겠다고 정중하게 여쭙는다. 지점으로 오시라고 하지 않는다.
규칙:
1. facts·call_reason·call_purpose에 있는 내용만 말한다. 그 밖의 사실·수치·날짜·혜택을 만들지 마라.
2. 금융상품 이름이나 대출·금리·한도·수익·수수료를 안내하거나 권유하지 마라. '확정 수익', '원금 보장' 같은 표현을 쓰지 마라.
3. 개인에 대한 정보를 추측하거나 언급하지 마라.
4. 존댓말로 정확히 3문장. 한 문장은 50자 안팎으로 짧게 쓰고 '~하고자' 같은 문어체를 피한다. 출처 태그나 대괄호는 쓰지 마라.
5. script 배열의 각 원소는 정확히 한 문장이어야 한다.
6. '문을 여신'처럼 '여신'이 들어가는 존댓말은 상품 용어로 오인되어 차단되므로 '개업하신', '여셨다'로 쓴다.
7. 연도·날짜·거리·건수·반경 같은 숫자는 쓰지 마라. 예외: 환율·유가 변동률과 그 기준일(예: 10월 7일)은 facts에 적힌 그대로 한 번 쓸 수 있다.
8. '인허가', '확인', '조회', '반경', '데이터'처럼 정보를 찾아본 티가 나는 말을 쓰지 마라. 주변 경쟁 매장 이야기도 하지 마라.
9. facts가 기상청 예보이면 "예보가 있어"처럼 예보임을 밝힌다. 단정하지 마라.
10. 1문장은 "안녕하세요 사장님, {org_name} {branch_name}에서 … 연락드렸습니다."처럼 한 문장으로 잇는다. "~입니다," 처럼 종결어미 뒤에 쉼표를 붙여 문장을 이어 쓰지 마라.
11. 출력은 JSON 한 개만: {"script": ["문장1", "문장2", "문장3"]}"""



def polish_greeting(script: list[str], org_name: str, branch_name: str) -> list[str]:
    """첫 문장의 '{기관} {지점}입니다, ' 를 '{기관} {지점}에서 ' 로 바꾼다. 내용(사실·수치)은 바꾸지 않는다."""
    if not script:
        return script
    first = script[0]
    for prefix in (f"{org_name} {branch_name}", branch_name):
        first = re.sub(re.escape(prefix) + r"입니다,\s*", f"{prefix}에서 ", first, count=1)
    return [first, *script[1:]]


def _call_reason(brief_input: BriefInput) -> str:
    return brief_input.call_reason.strip() or _FALLBACK_CALL_REASON


def _call_purpose(brief_input: BriefInput) -> str:
    return brief_input.call_purpose.strip() or _FALLBACK_CALL_PURPOSE


def build_user_prompt(brief_input: BriefInput, config: BriefingConfig) -> str:
    """LLM 입력 — 핵심 근거(첫 번째 사실) 1개와 업종 마지막 단계만 넘긴다(10/14 테스트 결과 10-3).

    근거를 여러 개 주면 거리·건수·인허가일 같은 숫자를 화법에 끌어 쓴다. 검증(validate_script)은 전체 facts로 한다.
    """
    return json.dumps(
        {
            "org_name": config.greeting_org_name,
            "branch_name": brief_input.branch_name,
            "business_name": brief_input.business_name,
            "industry": _industry_leaf(brief_input.industry_name),
            "call_reason": _call_reason(brief_input),
            "call_purpose": _call_purpose(brief_input),
            "facts": [fact.text for fact in brief_input.facts[:1]],
        },
        ensure_ascii=False,
    )


def template_script(brief_input: BriefInput, config: BriefingConfig) -> list[str]:
    """정형 화법(LLM 미가용 시) — 인사·연락 사유 / 연락 목적 / 다음 행동 요청 3문장.

    사유·목적 문구는 fact_builder가 신호 종류별로 정한 고정 문구이며, 수치를 담더라도 사실 문장과 같은 값이다.
    """
    return [
        f"안녕하세요 {brief_input.business_name} 사장님, {config.greeting_org_name} {brief_input.branch_name}에서 "
        f"{_call_reason(brief_input)} 연락드렸습니다.",
        f"{_call_purpose(brief_input)} 합니다.",
        _CALL_ASK,
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


def parse_llm_script_strict(raw: str) -> list[str]:
    """실제 LLM 응답의 strict JSON 계약을 검증하고 안전한 오류로 통일한다."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise LlmUnavailableError("LLM 응답 형식이 올바르지 않습니다") from None

    script = data.get("script") if isinstance(data, dict) else None
    if (
        not isinstance(script, list)
        or not script
        or any(not isinstance(line, str) or not line.strip() for line in script)
    ):
        raise LlmUnavailableError("LLM 응답 형식이 올바르지 않습니다")
    return script


def generate_brief(
    brief_input: BriefInput,
    *,
    reason_summary: str,
    llm: LlmClient | None,
    config: BriefingConfig,
) -> BriefContent:
    facts, errors = validate_facts(brief_input.facts, config)
    allowed_context = [
        brief_input.branch_name,
        brief_input.business_name,
        config.greeting_org_name,
        _call_reason(brief_input),
        _call_purpose(brief_input),
    ]
    checklist = list(config.default_checklist)
    user_prompt = build_user_prompt(brief_input.model_copy(update={"facts": facts}), config)
    prompt_record = f"[{PROMPT_VERSION}]\n[system]\n{SYSTEM_PROMPT}\n[user]\n{user_prompt}"

    if llm is not None:
        started = time.monotonic()
        try:
            result = llm.complete(SYSTEM_PROMPT, user_prompt, max_tokens=config.max_output_tokens)
            latency_ms = int((time.monotonic() - started) * 1000)
            script, script_errors = validate_script(
                polish_greeting(
                    parse_llm_script_strict(result.text), config.greeting_org_name, brief_input.branch_name
                ),
                facts,
                config,
                allowed_context=allowed_context,
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
            errors.append(f"LLM 호출 실패 — 정형 화법으로 대체 ({type(exc).__name__})")
        except Exception as exc:  # noqa: BLE001 — LLM 응답 파싱·검증 실패도 브리프 한 건 안에서 격리한다.
            errors.append(f"브리프 생성 예외 — 정형 화법으로 대체 ({type(exc).__name__})")

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
