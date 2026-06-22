"""공통 LLM 결과/사용량 타입 (M-7 이원화 정리).

두 클라이언트(form_filler.llm_client = 동기 Anthropic SDK, playground.tencent_aigc_client
= async 스트리밍)는 호출/스트리밍 방식이 근본적으로 달라 **통합하지 않는다**(스코프 밖).
다만 토큰 사용량 집계의 공통 형태를 한 곳에 정의해, 추후 메트릭/로깅 통합 시 단일 소스로 쓸 수 있게 한다.

NOTE (보수적 MVP — 동작 변경 0):
- 기존 ``form_filler.llm_client.LLMResponse`` dataclass 는 그대로 유지한다(호출부 무변경).
  이 모듈의 타입은 신규 코드/공통 집계용이며, 기존 두 클라이언트의 반환 형태를 바꾸지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMUsage:
    """LLM 토큰 사용량 — provider 공통 정규화 형태.

    두 클라이언트 모두 노출하는 4개 필드를 공통 분모로 모은다.
    - Anthropic: input/output/cache_read/cache_creation 모두 제공.
    - Tencent(OpenAI 호환): cache_creation 개념 없음 → 0 으로 둠.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


__all__ = ["LLMUsage"]
