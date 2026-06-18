"""LLM 가격/모델 단가의 단일 소스 (M-7 이원화 정리).

이 모듈은 TK101 의 **두 LLM 클라이언트**(form_filler.llm_client = Anthropic SDK 직접
호출, playground.tencent_aigc_client = Tencent MaaS OpenAI 호환)가 **공유하는** 단가표와
비용 계산 로직을 한 곳에 모은다.

설계 원칙 (보수적 MVP — 동작 변경 0):
- provider 별 dict 로 단가를 분리한다. 값은 기존 두 클라이언트의 값을 **그대로** 옮긴 것이며
  변경하지 않는다(회귀 방지).
  - ``ANTHROPIC_TEXT_PRICING``: Anthropic SDK 직접 호출(form_filler/docgen)이 쓰던
    ``(input, output)`` USD/1M 단가. (구 ``llm_client._MODEL_PRICING``)
  - ``TENCENT_TEXT_PRICING`` / ``TENCENT_IMAGE_PRICING`` / ``TENCENT_VIDEO_PRICING_PER_SEC``:
    Tencent MaaS 단가(2026-05-19 엑셀 기준). (구 ``playground.pricing``)
- 계산 함수도 기존 동작을 보존한다:
  - ``estimate_anthropic_cost``: float, round 6 자리. cache_read 는 input 단가의 10%.
  - ``calc_tencent_text_cost``: Decimal, 6 자리. cached_tokens 는 input 에서 차감 후 cache rate.
  - ``calc_tencent_image_cost`` / ``calc_tencent_video_cost``: Decimal, 6 자리.

기존 모듈(``form_filler.llm_client``, ``playground.pricing``)은 이 모듈로 위임/재export 하여
호출부 시그니처를 100% 유지한다.

모든 단가는 USD.
"""
from __future__ import annotations

from decimal import Decimal

# ---------------------------------------------------------------------------
# Anthropic — USD per 1M tokens (input, output)
# form_filler/docgen 가 Anthropic SDK 로 직접 호출하는 모델. PRD NFR-02 가정.
# (구 form_filler.llm_client._MODEL_PRICING — 값 보존)
# ---------------------------------------------------------------------------
ANTHROPIC_TEXT_PRICING: dict[str, tuple[float, float]] = {
    # Sonnet 4.6: input $3.00, output $15.00
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),  # 호환
    # Haiku 4.5: input $1.00, output $5.00
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),  # 호환
}

# Anthropic 모델 단가 미등록 시 기본값 (Sonnet 4.6 단가).
_ANTHROPIC_DEFAULT_RATES: tuple[float, float] = (3.00, 15.00)

# Anthropic prompt-caching: cache read 는 input 단가의 10% (Anthropic 정책 가정).
_ANTHROPIC_CACHE_READ_FACTOR: float = 0.1


# ---------------------------------------------------------------------------
# Tencent MaaS — USD per 1M tokens (input, cache_read, output)
# 출처: ``업무개선요구사항/AI 플레이그라운드/[Mpaas_AIGC] Model List and Quotation ...xlsx``
# (구 playground.pricing.TEXT_PRICING — 값 보존)
#
# 단순화:
# - LLM long-context 분기 (>32K, >200K) 는 기본 단가만 사용. 정확한 분기는 추후.
# - 이미지는 1K 기본 단가 (사용자가 옵션 안 주면 1K 가정).
# - 영상은 720P 기본 단가 (현재 디폴트). Hailuo 768P 는 720P 와 같이 사용.
# ---------------------------------------------------------------------------
TENCENT_TEXT_PRICING: dict[str, tuple[float, float, float]] = {
    "gpt-5-chat": (1.25, 0.125, 10.0),
    # 2026-05-20 신규: 텐센트 단가 스냅샷 미수신 — OpenAI 공식가 ($2/$0.5/$8) 잠정 적용.
    # 청구액은 텐센트 콘솔이 진실. dump_pricing.py 갱신 시 교체.
    "gpt-4.1": (2.0, 0.5, 8.0),
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
    # 2026-05-20 신규: m2.7 와 동일 단가 잠정 적용. 텐센트 콘솔 청구액으로 보정.
    "minimax-m2.5": (0.3, 0.06, 1.2),
    "deepseek-v3.2": (0.28, 0.028, 0.42),
}


# ---------------------------------------------------------------------------
# Tencent 이미지 — USD per generated image (1K 기본)
# (구 playground.pricing.IMAGE_PRICING — 값 보존)
# ---------------------------------------------------------------------------
TENCENT_IMAGE_PRICING: dict[str, float] = {
    "Kling:2.1": 0.014,
    "Kling:3.0": 0.028,
    "Seedream:4.5": 0.038,
    "Seedream:5.0-lite": 0.034,
    "Qwen:0925": 0.046,
    "Jimeng:4.0": 0.034,
}


# ---------------------------------------------------------------------------
# Tencent 영상 — USD per second (720P 기본)
# (구 playground.pricing.VIDEO_PRICING_PER_SEC — 값 보존)
# ---------------------------------------------------------------------------
TENCENT_VIDEO_PRICING_PER_SEC: dict[str, float] = {
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


# ===========================================================================
# 비용 계산 — Anthropic (form_filler/docgen 경로)
# ===========================================================================
def estimate_anthropic_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
) -> float:
    """간이 비용 추정 — cache read 는 input 단가의 10% 가정 (Anthropic 정책).

    구 ``form_filler.llm_client._estimate_cost`` 와 동일한 동작 (float, round 6자리).
    """
    in_price, out_price = ANTHROPIC_TEXT_PRICING.get(model, _ANTHROPIC_DEFAULT_RATES)
    cost = (input_tokens / 1_000_000) * in_price
    cost += (output_tokens / 1_000_000) * out_price
    cost += (cache_read_tokens / 1_000_000) * in_price * _ANTHROPIC_CACHE_READ_FACTOR
    return round(cost, 6)


# ===========================================================================
# 비용 계산 — Tencent MaaS (playground 경로)
# ===========================================================================
def _q(value: float) -> Decimal:
    """Decimal로 6자리. 누적 합산 시 부동소수점 오차 회피."""
    return Decimal(repr(value)).quantize(Decimal("0.000001"))


def calc_tencent_text_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None = None,
) -> Decimal | None:
    """모델 + 토큰 → USD. 단가 미등록 모델은 None.

    구 ``playground.pricing.calc_text_cost`` 와 동일한 동작.
    """
    if not model:
        return None
    rates = TENCENT_TEXT_PRICING.get(model)
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


def calc_tencent_image_cost(model_key: str | None) -> Decimal | None:
    """이미지 1장 생성 비용. 단가 미등록 모델은 None.

    구 ``playground.pricing.calc_image_cost`` 와 동일한 동작.
    """
    if not model_key:
        return None
    rate = TENCENT_IMAGE_PRICING.get(model_key)
    return _q(rate) if rate is not None else None


def calc_tencent_video_cost(
    model_key: str | None, duration_sec: int | None
) -> Decimal | None:
    """영상 생성 비용 = (per-sec 단가) × 길이. 단가 미등록 모델은 None.

    구 ``playground.pricing.calc_video_cost`` 와 동일한 동작.
    """
    if not model_key:
        return None
    rate = TENCENT_VIDEO_PRICING_PER_SEC.get(model_key)
    if rate is None:
        return None
    dur = int(duration_sec or 0)
    return (_q(rate) * Decimal(dur)).quantize(Decimal("0.000001"))


__all__ = [
    # Anthropic
    "ANTHROPIC_TEXT_PRICING",
    "estimate_anthropic_cost",
    # Tencent
    "TENCENT_TEXT_PRICING",
    "TENCENT_IMAGE_PRICING",
    "TENCENT_VIDEO_PRICING_PER_SEC",
    "calc_tencent_text_cost",
    "calc_tencent_image_cost",
    "calc_tencent_video_cost",
]
