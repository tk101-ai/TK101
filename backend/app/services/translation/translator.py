"""중→한 번역 서비스 (체험단 후기, 업무개선요구사항 #17).

설계 결정:
- form_filler.llm_client.call_claude 를 그대로 재사용 — Langfuse 트레이스, prompt caching,
  비용 추정이 이미 내장. 별도 SDK 호출 경로를 만들면 정책 분기가 늘어남.
- 기본 모델: Haiku 4.5 (NFR-02 비용 절감). 호출자 선택으로 Sonnet 가능.
- system 프롬프트는 cache_system=True로 ephemeral 캐시 — 동일 시스템 프롬프트 반복 호출 시
  prompt caching이 input 토큰 비용을 절감 (Anthropic 정책상 5분 TTL).
- 반환 타입은 form_filler.llm_client.LLMResponse 그대로 사용 — dict 변환 시 키 오타가
  런타임까지 잡히지 않아 타입 안전성 손실 (H-C4).
- 사용자별 분당 호출 한도(인메모리 카운터) — Anthropic API 비용 폭주 차단 (H-C2).
  단일 백엔드 인스턴스 운영 전제. 멀티-인스턴스로 확장 시 Redis 등 외부 카운터로 교체.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Literal

from app.config import settings
from app.services.llm.client import LLMResponse, call_claude

logger = logging.getLogger(__name__)

ModelChoice = Literal["haiku", "sonnet"]

# 시스템 프롬프트: 마케팅 톤 보존 + 자연스러운 한국어 + 이모지/구두점 유지.
# 첫 줄 영어 — 일부 모델이 한국어 system 프롬프트보다 영어 system 프롬프트를 일관되게 따르는 경향.
SYSTEM_PROMPT = (
    "You are a professional Chinese-to-Korean translator specializing in product reviews "
    "and social media content. Translate the given Chinese text into natural, fluent Korean "
    "suitable for marketing review archives. Preserve the original tone and emoji where "
    "appropriate. Output only the Korean translation — no explanations, no source text, "
    "no quotation marks around the result."
)


# ---------------------------------------------------------------------------
# Rate limiter (H-C2) — 사용자별 인메모리 슬라이딩 윈도우.
# ---------------------------------------------------------------------------

# 분당 허용 호출 횟수. 평균 1건 5초 가정 → 12건/분이 자연스러운 사용 상한.
# 30회/분은 비정상 패턴(스크립트/연속 클릭) 차단용 안전 마진.
_RATE_LIMIT_MAX_CALLS = 30
_RATE_LIMIT_WINDOW_SEC = 60

# user_id → 최근 호출 타임스탬프(epoch sec) deque.
# 단일 프로세스 내 락으로 race 조건 차단.
_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = {}


class RateLimitExceeded(Exception):
    """사용자별 분당 호출 한도 초과. 라우터에서 429로 매핑."""


def check_rate_limit(
    user_id: str,
    *,
    max_calls: int = _RATE_LIMIT_MAX_CALLS,
    window_sec: int = _RATE_LIMIT_WINDOW_SEC,
) -> None:
    """사용자별 슬라이딩 윈도우 레이트리밋.

    호출 시점 기준으로 window_sec 안의 호출 수가 max_calls 이상이면 RateLimitExceeded.
    통과 시 현재 시각을 버킷에 추가.

    Args:
        user_id: 사용자 식별자(문자열). UUID 등.
        max_calls: 윈도우당 최대 호출 수.
        window_sec: 윈도우 크기(초).

    Raises:
        RateLimitExceeded: 한도 초과.
    """
    now = time.monotonic()
    cutoff = now - window_sec
    with _rate_lock:
        bucket = _rate_buckets.get(user_id)
        if bucket is None:
            bucket = deque()
            _rate_buckets[user_id] = bucket
        # cutoff 이전 타임스탬프 제거.
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_calls:
            raise RateLimitExceeded(
                f"user={user_id} 분당 호출 {max_calls}회 한도 초과"
            )
        bucket.append(now)


def _select_model(choice: ModelChoice) -> str:
    """모델 라우팅. settings의 form_filler_* 설정을 재사용 — 별도 env 변수를 늘리지 않는다."""
    if choice == "sonnet":
        return settings.form_filler_sonnet_model
    return settings.form_filler_haiku_model


def translate_chinese_to_korean(
    text: str,
    *,
    model: ModelChoice = "haiku",
    user_id: str | None = None,
) -> LLMResponse:
    """중국어 원문을 한국어로 번역.

    Args:
        text: 중국어 원문. 빈 문자열은 호출자가 사전 검증.
        model: 'haiku'(기본, 비용 절감) | 'sonnet'(품질 우선)
        user_id: Langfuse trace metadata 기록용. 옵션.

    Returns:
        LLMResponse — text(번역문), input_tokens, output_tokens, cost_usd,
        model, trace_id, cache_read_tokens, cache_creation_tokens.

    Raises:
        RuntimeError: ANTHROPIC_API_KEY 미설정 또는 SDK 호출 실패.
        ValueError: 번역 결과가 비어있는 경우.
    """
    if not text or not text.strip():
        raise ValueError("원문 텍스트가 비어있습니다")

    selected_model = _select_model(model)

    # 본문은 그대로 전달. 후처리에서 LLM이 따옴표/설명을 붙이면 strip.
    user_message = f"다음 중국어 텍스트를 한국어로 번역하세요:\n\n{text}"

    response: LLMResponse = call_claude(
        system_prompt=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        model=selected_model,
        max_tokens=4096,
        cache_system=True,
        cache_user_first=False,
        trace_name="review_translation",
        trace_metadata={"user_id": user_id, "source_chars": len(text)},
    )

    translated = response.text.strip()
    # LLM이 가끔 따옴표로 감싸는 경우 제거 (system 프롬프트로 차단했지만 방어적).
    if (translated.startswith('"') and translated.endswith('"')) or (
        translated.startswith("「") and translated.endswith("」")
    ):
        translated = translated[1:-1].strip()

    if not translated:
        raise ValueError("번역 결과가 비어있습니다 — 원문 또는 모델 응답 확인 필요")

    # LLMResponse는 frozen=True dataclass — text 후처리분만 dataclasses.replace로 교체.
    # 직접 mutate 불가하므로 새 인스턴스 반환.
    from dataclasses import replace

    return replace(response, text=translated)
