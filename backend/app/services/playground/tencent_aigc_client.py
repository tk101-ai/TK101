"""Tencent MPaaS AIGC OpenAI-compatible SSE 스트림 어댑터 (T8 Phase 1).

설계 결정:
- 텐센트 MPaaS AIGC 는 **OpenAI Chat Completions 호환** endpoint 1개 (`/v1/chat/completions`) 로
  Claude / GPT / Gemini / Grok / Kimi / GLM / MiniMax / DeepSeek 8 공급자 + 모든 변형을 노출.
- 따라서 SDK 도 ``openai>=1.50`` 1개만 사용. Provider 분기는 ``model`` 파라미터로만.
- Phase 3 에서 다른 공급자 model 식별자만 추가하면 코드 변경 없이 확장됨 (PRD 4절).

내부 chunk 포맷 (이전 ``claude_client`` 와 동일 — 라우터 그대로 재사용):
- ``{"type": "text_delta", "delta": "..."}``
- ``{"type": "usage", "input_tokens": int, "output_tokens": int,
      "cache_creation_input_tokens": 0, "cache_read_input_tokens": int}``
- ``{"type": "done"}``
- ``{"type": "error", "message": "..."}``

NOTE: Anthropic 의 ``cache_creation_input_tokens`` 구분은 OpenAI 표준에 없음.
- OpenAI ``prompt_tokens_details.cached_tokens`` → 우리 ``cache_read_input_tokens`` 로 매핑.
- ``cache_creation_input_tokens`` 는 0 으로 두어 라우터의 ``cached_total`` 합산 호환성 유지.

TENCENT_AIGC_API_KEY 미설정 시 ``RuntimeError``. 라우터가 503 으로 응답하게 함.

참고:
- 텐센트 공식 PPT 스펙 입수 전까지 ``BASE_URL`` / ``MODEL_*`` 상수는 추정치.
  사용자 PPT 수령 후 module-level 상수만 수정하면 끝.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 모델 식별자 — PPT 정식 spec 입수 전 placeholder.
# 사용자 PPT 수령 후 이 상수들만 수정하면 라우터/__init__/프론트엔드까지 자동 반영.
# ---------------------------------------------------------------------------
MODEL_CLAUDE_HAIKU = "claude-haiku-4-5"
MODEL_CLAUDE_SONNET = "claude-sonnet-4-6"
MODEL_CLAUDE_OPUS = "claude-opus-4-7"


def _build_async_client() -> Any:
    """AsyncOpenAI 클라이언트 lazy import. 키 없으면 RuntimeError."""
    if not settings.tencent_aigc_api_key:
        raise RuntimeError(
            "TENCENT_AIGC_API_KEY 환경변수가 설정되지 않았습니다. Playground 사용 불가."
        )
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            f"openai SDK 미설치: pip install openai>=1.50. 원인: {exc}"
        ) from exc
    return AsyncOpenAI(
        api_key=settings.tencent_aigc_api_key,
        base_url=settings.tencent_aigc_base_url,
    )


async def stream_chat(
    *,
    messages: list[dict],
    model: str,
    system_prompt: str | None,
    temperature: float,
    max_tokens: int = 4096,
) -> AsyncIterator[dict]:
    """텐센트 MPaaS AIGC Chat Completions streaming 호출.

    Args:
        messages: ``[{"role": "user"|"assistant", "content": "..."}]`` 시간순.
        model: 정확한 모델 ID (예: ``claude-haiku-4-5``). ``MODEL_*`` 상수 참조.
        system_prompt: None 또는 빈 문자열이면 생략. 있으면 OpenAI 표준대로
                       ``messages`` 맨 앞에 ``{"role": "system"}`` 으로 prepend.
        temperature: 0.0 ~ 1.0.
        max_tokens: 응답 최대 토큰.

    Yields:
        dict: 위 docstring 참고.
    """
    client = _build_async_client()

    # OpenAI 표준: system 은 별도 인자가 아니라 messages 배열의 첫 원소.
    api_messages: list[dict] = []
    if system_prompt:
        api_messages.append({"role": "system", "content": system_prompt})
    api_messages.extend(messages)

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=api_messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            # 마지막 chunk 에 usage 포함 — 토큰 메트릭 수집에 필수.
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            # 1) 텍스트 델타 추출 — choices[0].delta.content.
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    yield {"type": "text_delta", "delta": content}

            # 2) usage 는 stream_options.include_usage=True 일 때 마지막 chunk 에 옴.
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                # OpenAI 표준 필드명: prompt_tokens, completion_tokens, total_tokens.
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
                # cached_tokens 는 prompt_tokens_details 하위에 있음 (OpenAI 신표준).
                cached = 0
                details = getattr(usage, "prompt_tokens_details", None)
                if details is not None:
                    cached = int(getattr(details, "cached_tokens", 0) or 0)
                yield {
                    "type": "usage",
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    # OpenAI 표준엔 cache_creation 개념 없음 — 0 으로 둠.
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": cached,
                }
    except Exception as exc:  # noqa: BLE001 — 외부 API 실패는 error chunk 로 정규화.
        logger.exception("Tencent AIGC streaming 호출 실패")
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "done"}
