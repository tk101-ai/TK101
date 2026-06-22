"""공통 LLM 모듈 (M-7 클라이언트 이원화 정리).

TK101 은 두 LLM 클라이언트를 운영한다:
- ``app.services.llm.client``: Anthropic SDK 동기 호출 (form_filler/docgen).
- ``app.services.playground.tencent_aigc_client``: Tencent MaaS OpenAI 호환 async 스트리밍 (playground).

이 패키지는 두 클라이언트가 **공유**하는 횡단 관심사를 단일 소스로 모은다:
- ``pricing``: provider 별 단가표 + 비용 계산 (Anthropic / Tencent).
- ``types``: 공통 LLMUsage / LLMResult dataclass (집계용 신규 타입).

스트리밍 방식 차이(동기 vs async)는 통합하지 않는다 — 가격/모델ID/사용량 집계의
단일 소스화까지만 담당한다.
"""
from app.services.llm import pricing, types
from app.services.llm.pricing import (
    ANTHROPIC_TEXT_PRICING,
    TENCENT_IMAGE_PRICING,
    TENCENT_TEXT_PRICING,
    TENCENT_VIDEO_PRICING_PER_SEC,
    calc_tencent_image_cost,
    calc_tencent_text_cost,
    calc_tencent_video_cost,
    estimate_anthropic_cost,
)
from app.services.llm.types import LLMResult, LLMUsage

__all__ = [
    "pricing",
    "types",
    "ANTHROPIC_TEXT_PRICING",
    "TENCENT_TEXT_PRICING",
    "TENCENT_IMAGE_PRICING",
    "TENCENT_VIDEO_PRICING_PER_SEC",
    "estimate_anthropic_cost",
    "calc_tencent_text_cost",
    "calc_tencent_image_cost",
    "calc_tencent_video_cost",
    "LLMUsage",
    "LLMResult",
]
