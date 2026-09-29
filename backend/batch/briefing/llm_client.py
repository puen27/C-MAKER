"""LiteLLM Gateway(OpenAI-Compatible) 호출 래퍼 (docs/10-implementation-guide.md §8).

생성형 AI 호출은 briefing 모듈에서만 발생한다(OPS-06). 입력에는 개인 고객정보가 없다 — 공개 데이터
기반 사실 문장과 지점명·상호만 들어간다(RULE-SEC-01).

⚠ CLAUDE.md §8-1: 명부 데이터의 외부 반출 경로(리전·네트워크)는 보안팀 승인 전이다. 게이트웨이 주소는
.env(LLM_BASE_URL)로만 주입하며 코드에 고정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

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
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,  # 브리프 1건 5초 이내(UC-07)
            max_retries=1,
        )

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int) -> LlmResult:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0,  # 재현성(PRIN-08) — 같은 입력이면 최대한 같은 출력
            )
        except OpenAIError as exc:
            raise LlmUnavailableError(f"{type(exc).__name__}: {exc}") from exc
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LlmUnavailableError("빈 응답")
        return LlmResult(text=content, model=response.model or self._model)


def create_llm_client(settings: Settings) -> LlmClient | None:
    try:
        return LlmClient(settings)
    except LlmUnavailableError:
        return None
