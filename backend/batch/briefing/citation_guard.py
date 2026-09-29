"""그라운딩 검증 (RULE-BRIEF-01~03, CLAUDE.md §0.3·§0.8).

docs/10-implementation-guide.md §8.3은 "프롬프트 지시 + 출처 태그 포맷 강제, 후처리 검증 없음"으로 적고 있으나,
CLAUDE.md 절대 원칙 3("도구 결과에 없는 사실을 생성한 문장은 표시 전 검증 단계에서 반드시 차단")을 지키기 위해
가벼운 결정론적 검증을 둔다.

- 사실 문장: 출처 태그 형식(`소스명·YYYY-MM-DD`)이 없으면 제거한다.
- 화법 문장: 사실 문장에 없는 수치·날짜, 금칙 표현(확정 수익·원금 보장 등), 상품 안내 용어(MVP에는 상품설명서
  RAG가 없어 인용 문단 ID를 붙일 수 없음)를 포함하면 문장을 차단한다. 최대 3문장.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from backend.common.config import BriefingConfig
from backend.common.schemas.brief import BriefFact

SOURCE_TAG_PATTERN = re.compile(r"^[^·\[\]\s][^·\[\]]*·\d{4}-\d{2}-\d{2}$")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_BRACKETED = re.compile(r"\[[^\]]*\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")


def _numbers(text: str) -> set[str]:
    return {token.replace(",", "") for token in _NUMBER.findall(text)}


def contains_forbidden(text: str, config: BriefingConfig) -> str | None:
    compact = text.replace(" ", "")
    for expression in config.forbidden_expressions:
        if expression.replace(" ", "") in compact:
            return expression
    return None


def validate_facts(facts: list[BriefFact], config: BriefingConfig) -> tuple[list[BriefFact], list[str]]:
    kept: list[BriefFact] = []
    errors: list[str] = []
    for fact in facts:
        if not fact.text.strip() or not SOURCE_TAG_PATTERN.match(fact.source_tag):
            errors.append(f"출처 태그 없는 사실 문장 제거: {fact.text[:40]}")
            continue
        forbidden = contains_forbidden(fact.text, config)
        if forbidden:
            errors.append(f"금칙 표현 포함 사실 문장 제거: {forbidden}")
            continue
        kept.append(fact)
    return kept, errors


def split_sentences(lines: Iterable[str]) -> list[str]:
    sentences: list[str] = []
    for line in lines:
        for part in _SENTENCE_SPLIT.split(line.strip()):
            part = part.strip().strip('"“”').strip()
            if part:
                sentences.append(part)
    return sentences


def validate_script(
    lines: list[str],
    facts: list[BriefFact],
    config: BriefingConfig,
    *,
    allowed_context: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    """(통과한 화법 문장, 차단 사유). `allowed_context`는 지점명·상호 등 입력으로 준 고유 텍스트."""
    allowed_numbers: set[str] = set()
    for text in [fact.text for fact in facts] + list(allowed_context):
        allowed_numbers |= _numbers(text)

    kept: list[str] = []
    errors: list[str] = []
    for sentence in split_sentences(lines):
        sentence = _BRACKETED.sub("", sentence).strip()
        if not sentence:
            continue
        forbidden = contains_forbidden(sentence, config)
        if forbidden:
            errors.append(f"금칙 표현 차단(RULE-BRIEF-03): {forbidden}")
            continue
        product = next((term for term in config.product_terms if term in sentence), None)
        if product:
            errors.append(f"상품 안내 차단(상품설명서 인용 없음): {product}")
            continue
        ungrounded = _numbers(sentence) - allowed_numbers
        if ungrounded:
            errors.append(f"근거 없는 수치 차단(RULE-BRIEF-02): {', '.join(sorted(ungrounded))}")
            continue
        kept.append(sentence)

    if len(kept) > config.max_script_sentences:
        errors.append(f"화법 {len(kept)}문장 → {config.max_script_sentences}문장으로 절삭")
        kept = kept[: config.max_script_sentences]
    return kept, errors
