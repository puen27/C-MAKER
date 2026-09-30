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
from decimal import Decimal, InvalidOperation

from backend.common.config import BriefingConfig
from backend.common.schemas.brief import BriefFact

SOURCE_TAG_PATTERN = re.compile(r"^[^·\[\]\s][^·\[\]]*·\d{4}-\d{2}-\d{2}$")
_NUMBER = re.compile(r"(?<![\d,.])[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)")
_NUMBER_SIGN_TRANSLATION = str.maketrans({"−": "-", "＋": "+", "－": "-", "﹣": "-"})
_BRACKETED = re.compile(r"\[[^\]]*\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")
_KEY_TOKEN = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}")
_COMMON_GROUNDING_TOKENS = frozenset(
    {
        "최근",
        "관련",
        "담당",
        "상권",
        "변화",
        "연락",
        "인사",
        "확인",
        "말씀",
        "사업장",
        "주변",
        "부분",
        "시간",
        "입니다",
        "있습니다",
        "드립니다",
        "드렸습니다",
        "되었습니다",
        "the",
        "and",
        "for",
        "with",
        "from",
    }
)
_KOREAN_PARTICLE_SUFFIXES = (
    "에서",
    "으로",
    "부터",
    "까지",
    "에게",
    "께서",
    "처럼",
    "보다",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "와",
    "과",
    "의",
    "도",
    "에",
)


def _numbers(text: str) -> set[Decimal]:
    """표현 차이(Unicode 부호·선행 0·쉼표·소수 끝 0)를 정규화해 비교한다."""
    normalized_text = text.translate(_NUMBER_SIGN_TRANSLATION)
    numbers: set[Decimal] = set()
    for token in _NUMBER.findall(normalized_text):
        try:
            numbers.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return numbers


def _format_number(number: Decimal) -> str:
    return format(number.normalize(), "f")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _normalize_key_token(token: str) -> str:
    normalized = token.lower()
    if re.fullmatch(r"[가-힣]+", normalized):
        for suffix in _KOREAN_PARTICLE_SUFFIXES:
            if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
                normalized = normalized[: -len(suffix)]
                break
    return normalized


def _key_tokens(text: str) -> set[str]:
    tokens = {_normalize_key_token(token) for token in _KEY_TOKEN.findall(text)}
    return {token for token in tokens if len(token) >= 2 and token not in _COMMON_GROUNDING_TOKENS}


def _select_grounded_sentences(
    sentences: list[str],
    facts: list[BriefFact],
    limit: int,
) -> list[str]:
    """근거와 수치·핵심 토큰이 겹치는 문장을 우선 선택하고 원래 순서를 유지한다."""
    if limit <= 0:
        return []

    fact_numbers: set[Decimal] = set()
    fact_tokens: set[str] = set()
    for fact in facts:
        fact_numbers |= _numbers(fact.text)
        fact_tokens |= _key_tokens(fact.text)

    relevant_indices = [
        index
        for index, sentence in enumerate(sentences)
        if (_numbers(sentence) & fact_numbers) or (_key_tokens(sentence) & fact_tokens)
    ]
    selected_indices = relevant_indices[:limit]
    if len(selected_indices) < limit:
        selected = set(selected_indices)
        selected_indices.extend(
            index for index in range(len(sentences)) if index not in selected
        )
        selected_indices = selected_indices[:limit]

    return [sentences[index] for index in sorted(selected_indices)]


def contains_forbidden(text: str, config: BriefingConfig) -> str | None:
    compact = _compact(text)
    for expression in config.forbidden_expressions:
        compact_expression = _compact(expression)
        if compact_expression and compact_expression in compact:
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
    allowed_numbers: set[Decimal] = set()
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
        compact_sentence = _compact(sentence)
        product = next(
            (
                term
                for term in config.product_terms
                if _compact(term) and _compact(term) in compact_sentence
            ),
            None,
        )
        if product:
            errors.append(f"상품 안내 차단(상품설명서 인용 없음): {product}")
            continue
        ungrounded = _numbers(sentence) - allowed_numbers
        if ungrounded:
            values = ", ".join(_format_number(number) for number in sorted(ungrounded))
            errors.append(f"근거 없는 수치 차단(RULE-BRIEF-02): {values}")
            continue
        kept.append(sentence)

    if len(kept) > config.max_script_sentences:
        errors.append(
            f"화법 {len(kept)}문장 → {config.max_script_sentences}문장으로 절삭"
            "(근거 연관 문장 우선 보존)"
        )
        kept = _select_grounded_sentences(kept, facts, config.max_script_sentences)
    return kept, errors
