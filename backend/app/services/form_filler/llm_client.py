"""Anthropic SDK 어댑터 + Langfuse 트레이스 + prompt caching.

PRD 6.3 / FR-09 / NFR-07 정책:
- 양식 분석/매핑/생성: Sonnet 4.6
- 단일 변수 재생성: Haiku 4.5 (자동, 비용 절감)
- system 프롬프트 + 양식 본문은 cache_control={"type": "ephemeral"}로 prompt caching
- Langfuse 트레이스 trace_id를 form_jobs.langfuse_trace_id에 저장

Anthropic API key가 없으면 (개발 환경) ImportError가 아니라 RuntimeError를 던져
호출자가 503으로 응답할 수 있게 한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    """Claude 호출 결과 정규화 페이로드."""

    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str
    trace_id: str | None
    cost_usd: float


# 모델별 단가 (USD/1M tokens). PRD NFR-02 가정.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Sonnet 4.6: input $3.00, output $15.00
    "claude-sonnet-4-6-20250929": (3.00, 15.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),  # 호환
    # Haiku 4.5: input $1.00, output $5.00
    "claude-haiku-4-5-20251022": (1.00, 5.00),
    "claude-haiku-4-5-20250714": (1.00, 5.00),  # 호환
}


def _estimate_cost(model: str, input_tok: int, output_tok: int, cache_read_tok: int) -> float:
    """간이 비용 추정 — cache read는 input 단가의 10% 가정 (Anthropic 정책)."""
    in_price, out_price = _MODEL_PRICING.get(model, (3.00, 15.00))
    cost = (input_tok / 1_000_000) * in_price
    cost += (output_tok / 1_000_000) * out_price
    cost += (cache_read_tok / 1_000_000) * in_price * 0.1
    return round(cost, 6)


def _build_anthropic_client() -> Any:
    """Anthropic SDK 클라이언트 lazy import. 키 없으면 RuntimeError."""
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. T5 양식 작성기 사용 불가."
        )
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            f"anthropic SDK 미설치: pip install anthropic. 원인: {exc}"
        ) from exc
    return Anthropic(api_key=settings.anthropic_api_key)


def _build_langfuse_client() -> Any | None:
    """Langfuse 클라이언트 lazy import. 시크릿 없으면 None (트레이스만 비활성화)."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse
    except ImportError:  # pragma: no cover
        logger.warning("langfuse SDK 미설치 — 트레이스 비활성화")
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def call_claude(
    *,
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4096,
    cache_system: bool = True,
    cache_user_first: bool = False,
    trace_name: str = "form_filler",
    trace_metadata: dict | None = None,
) -> LLMResponse:
    """Claude Messages API 동기 호출.

    Args:
        system_prompt: 시스템 프롬프트 텍스트
        messages: [{"role": "user", "content": "..."}] 형식
        model: 모델 ID. None이면 settings.form_filler_sonnet_model.
        max_tokens: 출력 최대 토큰
        cache_system: system을 cache_control ephemeral로 묶을지 (PRD 6.3)
        cache_user_first: 첫 user 메시지(보통 양식 본문)도 캐시할지
        trace_name: Langfuse 트레이스 이름
        trace_metadata: Langfuse 메타데이터 (job_id, template_id 등)

    Returns:
        LLMResponse — text, 토큰 카운트, 비용 추정, trace_id

    Raises:
        RuntimeError: API 키 없거나 SDK 호출 실패
    """
    selected_model = model or settings.form_filler_sonnet_model
    client = _build_anthropic_client()
    langfuse = _build_langfuse_client()

    # System block: 캐시 가능한 형태로 포장.
    if cache_system:
        system_blocks: list[dict] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        system_blocks = [{"type": "text", "text": system_prompt}]

    # User 메시지: 양식 본문 캐시가 필요하면 첫 메시지에 cache_control 부착.
    api_messages: list[dict] = []
    for idx, msg in enumerate(messages):
        if cache_user_first and idx == 0 and msg.get("role") == "user":
            api_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            )
        else:
            api_messages.append(msg)

    trace = None
    generation = None
    if langfuse is not None:
        try:
            trace = langfuse.trace(name=trace_name, metadata=trace_metadata or {})
            generation = trace.generation(
                name=f"{trace_name}.call",
                model=selected_model,
                input={"system": system_prompt, "messages": api_messages},
                metadata=trace_metadata or {},
            )
        except Exception:  # noqa: BLE001 - 트레이스 실패가 본 흐름을 막아선 안 됨
            logger.exception("Langfuse 트레이스 시작 실패 — 트레이스 없이 진행")
            trace = None
            generation = None

    try:
        response = client.messages.create(
            model=selected_model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=api_messages,
        )
    except Exception:
        if generation is not None:
            try:
                generation.end(level="ERROR")
            except Exception:  # noqa: BLE001
                pass
        raise

    # 토큰 카운트 — usage 필드 형식이 SDK 버전에 따라 약간 다를 수 있어 방어적 추출.
    usage = getattr(response, "usage", None)
    input_tok = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
    output_tok = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0) if usage else 0
    cache_create = (
        int(getattr(usage, "cache_creation_input_tokens", 0) or 0) if usage else 0
    )
    cost = _estimate_cost(selected_model, input_tok, output_tok, cache_read)

    # content 블록 합치기.
    text_parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text_parts.append(getattr(block, "text", "") or "")
    text = "".join(text_parts)

    trace_id = None
    if generation is not None:
        try:
            generation.end(
                output=text,
                usage={
                    "input": input_tok,
                    "output": output_tok,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_create,
                    "total_cost": cost,
                },
            )
            trace_id = trace.id if trace is not None else None
        except Exception:  # noqa: BLE001
            logger.exception("Langfuse 트레이스 종료 실패")

    return LLMResponse(
        text=text,
        input_tokens=input_tok,
        output_tokens=output_tok,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_create,
        model=selected_model,
        trace_id=trace_id,
        cost_usd=cost,
    )
