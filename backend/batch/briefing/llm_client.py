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
            raise LlmUnavailableError(f"{type(exc).__name__}: {exc}") from exc
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else None
        if not content:
            reason = choice.finish_reason if choice else "no_choices"
            raise LlmUnavailableError(f"빈 응답 (finish_reason={reason})")
        return LlmResult(text=content, model=response.model or self._model)


def create_llm_client(settings: Settings) -> LlmClient | None:
    try:
        return LlmClient(settings)
    except LlmUnavailableError:
        return None
