"""LiteLLM Gateway(OpenAI-Compatible) 호출 래퍼 (docs/10-implementation-guide.md §8).

생성형 AI 호출은 briefing 모듈에서만 발생한다(OPS-06). 입력에는 개인 고객정보가 없다 — 공개 데이터
기반 사실 문장과 지점명·상호만 들어간다(RULE-SEC-01).

⚠ CLAUDE.md §8-1: 명부 데이터의 외부 반출 경로(리전·네트워크)는 보안팀 승인 전이다. 게이트웨이 주소는
.env(LLM_BASE_URL)로만 주입하며 코드에 고정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError

from backend.common.config import Settings


class LlmUnavailableError(RuntimeError):
    """게이트웨이 미설정·타임아웃·오류. 호출 측은 정형 화법으로 대체한다."""


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str


def _read_response_attribute(value: Any, name: str, *, default: Any = None) -> Any:
    """SDK 응답 필드를 안전하게 읽고 형식 오류를 게이트웨이 장애로 통일한다."""
    try:
        return getattr(value, name, default)
    except Exception:  # noqa: BLE001 — 외부 SDK 객체의 임의 속성 오류를 격리한다.
        raise LlmUnavailableError(f"잘못된 LLM 응답 형식 ({name})") from None


def _parse_completion_response(response: Any, fallback_model: str) -> LlmResult:
    """OpenAI-compatible 응답 구조를 검증해 안전한 내부 계약으로 변환한다."""
    choices = _read_response_attribute(response, "choices")
    if not isinstance(choices, list) or not choices:
        raise LlmUnavailableError("잘못된 LLM 응답 형식 (choices)")

    message = _read_response_attribute(choices[0], "message")
    if message is None:
        raise LlmUnavailableError("잘못된 LLM 응답 형식 (message)")

    content = _read_response_attribute(message, "content")
    if not isinstance(content, str) or not content.strip():
        raise LlmUnavailableError("빈 LLM 응답 또는 잘못된 content 형식")

    model = _read_response_attribute(response, "model")
    if model is None or model == "":
        model = fallback_model
    if not isinstance(model, str):
        raise LlmUnavailableError("잘못된 LLM 응답 형식 (model)")

    return LlmResult(text=content, model=model)


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.llm_base_url or not settings.llm_api_key:
            raise LlmUnavailableError("LLM_BASE_URL / LLM_API_KEY가 설정되지 않았습니다")
        self._model = settings.llm_model
        self._disable_thinking = settings.llm_disable_thinking
        self._client = OpenAI(
            base_url=settings.llm_base_url,  # .../v1 까지 포함한 주소
            api_key=settings.llm_api_key,  # LiteLLM Virtual Key → Authorization: Bearer
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int) -> LlmResult:
        extra_body: dict[str, Any] = {}
        if self._disable_thinking:
            # extended thinking을 끄지 않으면 thinking 토큰이 max_tokens를 먼저 소진해
            # finish_reason="length" + content="" 가 돌아온다. reasoning_effort로는 꺼지지 않는다.
            extra_body["thinking"] = {"type": "disabled"}
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                # temperature는 보내지 않는다 — 게이트웨이의 claude-opus 계열은 temperature=1만
                # 허용하고 그 외 값은 400(litellm.UnsupportedParamsError)으로 거부한다.
                # 따라서 PRIN-08의 재현성은 temperature로 확보할 수 없다(프롬프트 고정으로만 완화).
                extra_body=extra_body or None,
            )
        except OpenAIError as exc:
            # OpenAIError 원문에는 Virtual Key 식별자가 포함될 수 있어 DB 오류 기록으로 전달하지 않는다.
            raise LlmUnavailableError(f"LLM 게이트웨이 호출 실패 ({type(exc).__name__})") from exc
        return _parse_completion_response(response, self._model)


def create_llm_client(settings: Settings) -> LlmClient | None:
    try:
        return LlmClient(settings)
    except LlmUnavailableError:
        return None
