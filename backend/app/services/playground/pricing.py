"""Tencent MaaS 단가표 (2026-05-19 엑셀 기준).

출처: ``업무개선요구사항/AI 플레이그라운드/[Mpaas_AIGC] Model List and Quotation ...xlsx``

단순화:
- LLM long-context 분기 (>32K, >200K) 는 기본 단가만 사용. 정확한 분기는 추후.
- 이미지는 1K 기본 단가 (사용자가 옵션 안 주면 1K 가정).
- 영상은 720P 기본 단가 (현재 디폴트).
- Hailuo 768P 는 720P 와 같이 사용.

모든 단가는 USD.
"""
from __future__ import annotations

from decimal import Decimal


# ---------------------------------------------------------------------------
# LLM — USD per 1M tokens (input, cache_read, output)
# ---------------------------------------------------------------------------
TEXT_PRICING: dict[str, tuple[float, float, float]] = {
    "gpt-5-chat": (1.25, 0.125, 10.0),
    "gemini-2.5-flash": (0.3, 0.03, 2.5),
    "gemini-2.5-pro": (1.25, 0.125, 10.0),
    "gemini-3-flash-preview": (0.5, 0.05, 3.0),
    "gemini-3.1-pro-preview": (2.0, 0.2, 12.0),
    "gemini-3.1-flash-lite-preview": (0.25, 0.025, 1.5),
    "glm-5": (0.616, 0.154, 2.772),
    "glm-5.1": (0.924, 0.2, 3.696),
    "glm-5-turbo": (0.77, 0.185, 3.388),
    "kimi-k2.5": (0.616, 0.108, 3.234),
    "minimax-m2.7": (0.3, 0.06, 1.2),
    "deepseek-v3.2": (0.28, 0.028, 0.42),
}


# ---------------------------------------------------------------------------
# 이미지 — USD per generated image (1K 기본)
# ---------------------------------------------------------------------------
IMAGE_PRICING: dict[str, float] = {
    "Kling:2.1": 0.014,
    "Kling:3.0": 0.028,
    "Seedream:4.5": 0.038,
    "Seedream:5.0-lite": 0.034,
    "Qwen:0925": 0.046,
    "Jimeng:4.0": 0.034,
}


# ---------------------------------------------------------------------------
# 영상 — USD per second (720P 기본)
# ---------------------------------------------------------------------------
VIDEO_PRICING_PER_SEC: dict[str, float] = {
    "Kling:2.6": 0.042,
    "Kling:3.0": 0.084,
    "Kling:3.0-Omni": 0.084,
    "Kling:O1": 0.084,
    "Hailuo:02": 0.0508,
    "Hailuo:2.3": 0.0508,
    "Mingmou:1.0": 0.30,
    "Vidu:q2": 0.0492,
    "Vidu:q3": 0.10,
}


def _q(value: float) -> Decimal:
    """Decimal로 6자리. 누적 합산 시 부동소수점 오차 회피."""
    return Decimal(repr(value)).quantize(Decimal("0.000001"))


def calc_text_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None = None,
) -> Decimal | None:
    """모델 + 토큰 → USD. 단가 미등록 모델은 None."""
    if not model:
        return None
    rates = TEXT_PRICING.get(model)
    if not rates:
        return None
    in_r, cache_r, out_r = rates
    inp = int(input_tokens or 0)
    cached = int(cached_tokens or 0)
    # cached_tokens 는 input_tokens 안에 포함되어 있다고 가정 → 일반 input 에서 cache 차감 후 cache rate 적용.
    non_cached_input = max(inp - cached, 0)
    out = int(output_tokens or 0)
    cost = (
        Decimal(non_cached_input) * _q(in_r) / Decimal(1_000_000)
        + Decimal(cached) * _q(cache_r) / Decimal(1_000_000)
        + Decimal(out) * _q(out_r) / Decimal(1_000_000)
    )
    return cost.quantize(Decimal("0.000001"))


def calc_image_cost(model_key: str | None) -> Decimal | None:
    """이미지 1장 생성 비용. 단가 미등록 모델은 None."""
    if not model_key:
        return None
    rate = IMAGE_PRICING.get(model_key)
    return _q(rate) if rate is not None else None


def calc_video_cost(model_key: str | None, duration_sec: int | None) -> Decimal | None:
    """영상 생성 비용 = (per-sec 단가) × 길이. 단가 미등록 모델은 None."""
    if not model_key:
        return None
    rate = VIDEO_PRICING_PER_SEC.get(model_key)
    if rate is None:
        return None
    dur = int(duration_sec or 0)
    return (_q(rate) * Decimal(dur)).quantize(Decimal("0.000001"))


__all__ = [
    "TEXT_PRICING",
    "IMAGE_PRICING",
    "VIDEO_PRICING_PER_SEC",
    "calc_text_cost",
    "calc_image_cost",
    "calc_video_cost",
]
