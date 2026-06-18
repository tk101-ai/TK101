"""Tencent MaaS 단가표 (2026-05-19 엑셀 기준).

출처: ``업무개선요구사항/AI 플레이그라운드/[Mpaas_AIGC] Model List and Quotation ...xlsx``

M-7 (LLM 클라이언트 이원화 정리): 단가표/계산 로직은 ``app.services.llm.pricing`` 으로
단일 소스화되었다. 이 모듈은 **하위호환 facade** — 기존 호출부
(``app.routers.playground``)의 import 시그니처/반환 형태(Decimal, 6자리)를 100% 유지하기 위해
공통 모듈의 Tencent 단가/함수를 재export 한다. 동작 변경 없음.

단순화 (공통 모듈과 동일 가정):
- LLM long-context 분기 (>32K, >200K) 는 기본 단가만 사용. 정확한 분기는 추후.
- 이미지는 1K 기본 단가 (사용자가 옵션 안 주면 1K 가정).
- 영상은 720P 기본 단가 (현재 디폴트). Hailuo 768P 는 720P 와 같이 사용.

모든 단가는 USD.
"""
from __future__ import annotations

from app.services.llm.pricing import (
    TENCENT_IMAGE_PRICING,
    TENCENT_TEXT_PRICING,
    TENCENT_VIDEO_PRICING_PER_SEC,
    _q,
    calc_tencent_image_cost,
    calc_tencent_text_cost,
    calc_tencent_video_cost,
)

# 하위호환 별칭 — 기존 이름(TEXT_PRICING 등)을 그대로 노출. 값은 공통 모듈과 동일 객체.
TEXT_PRICING = TENCENT_TEXT_PRICING
IMAGE_PRICING = TENCENT_IMAGE_PRICING
VIDEO_PRICING_PER_SEC = TENCENT_VIDEO_PRICING_PER_SEC

# 계산 함수도 공통 모듈로 위임 (재export). 시그니처/반환(Decimal) 유지.
calc_text_cost = calc_tencent_text_cost
calc_image_cost = calc_tencent_image_cost
calc_video_cost = calc_tencent_video_cost


__all__ = [
    "TEXT_PRICING",
    "IMAGE_PRICING",
    "VIDEO_PRICING_PER_SEC",
    "calc_text_cost",
    "calc_image_cost",
    "calc_video_cost",
    "_q",
]
