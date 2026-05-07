"""Claude Haiku 4.5 기반 한국어 키워드 요약 생성기 (v0.7.x).

목적:
- 모든 NAS 파일에 대해 100~200자 한국어 키워드 요약을 생성
- chunk_index=-2 청크로 임베딩 저장해 검색 hit율 향상
- 검색 시점에 본문/파일명 청크와 동일하게 cosine 매칭됨

비용 추산 (12K 파일 기준):
- 입력 ~1K token + 출력 ~150 token × 12,000건
- Haiku 4.5: input $1.00/1M, output $5.00/1M
- 약 $15~20

설계 원칙:
- form_filler/llm_client.py와 별도 호출 경로 — 트레이스/캐시 정책이 다름.
  여기서는 단발성 짧은 호출이 12K번 반복되므로 prompt caching 효과가 거의 없고,
  Langfuse 트레이스가 12K건 쌓이면 노이즈만 늘어남. 그래서 직접 SDK 호출.
- 입력 길이 cap: 토큰 비용 제한 위해 본문을 30K자(~10K 토큰)로 자름.
- 빈 응답/에러 시 빈 문자열 반환 → caller가 skip.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# 입력 본문 길이 cap (한국어 기준 약 10K~15K token). Haiku 4.5 context는 200K지만
# 비용/속도 위해 cap. 평균 청크 텍스트가 이보다 짧으면 그대로 들어감.
MAX_INPUT_CHARS = 30_000

# 출력 max_tokens. 200자 한국어는 약 200~300 token이지만 여유 두기.
MAX_OUTPUT_TOKENS = 400

# Haiku 4.5 모델 ID. settings에 form_filler_haiku_model이 이미 같은 값.
HAIKU_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "당신은 한국어 문서 검색을 위한 키워드 요약 전문가입니다. "
    "주어진 문서에서 검색 시 hit해야 할 핵심 키워드(고유명사, 회사명, 제품명, "
    "날짜, 수치, 카테고리, 업무 분야, 주제어)를 100~200자의 한국어로 압축 요약합니다. "
    "일반 문장 대신 검색 가능한 단어 위주로 나열해도 좋습니다. "
    "추가 설명 없이 키워드 요약 본문만 출력하세요."
)


def _build_anthropic_client() -> Any:
    """Anthropic SDK 클라이언트 lazy import. 키 없으면 RuntimeError."""
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. 요약 backfill 사용 불가."
        )
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            f"anthropic SDK 미설치: pip install anthropic. 원인: {exc}"
        ) from exc
    return Anthropic(api_key=settings.anthropic_api_key)


def _truncate_for_input(text: str) -> str:
    """입력 길이 cap. 앞부분 우선(문서 핵심이 보통 앞쪽)."""
    if len(text) <= MAX_INPUT_CHARS:
        return text
    return text[:MAX_INPUT_CHARS]


def _call_haiku_sync(text: str, filename: str) -> str:
    """동기 Anthropic 호출. summarize_document에서 to_thread로 감싼다."""
    client = _build_anthropic_client()
    user_content = (
        f"파일명: {filename}\n\n"
        f"본문:\n{_truncate_for_input(text)}\n\n"
        f"→ 100~200자 한국어 키워드 요약:"
    )
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    summary = "".join(parts).strip()
    return summary


# 실패 시 재시도 정책 — Anthropic 일시적 rate limit / 네트워크 오류 대비.
RETRY_COUNT = 1
RETRY_DELAY_SEC = 3.0


async def summarize_document(text: str, filename: str) -> str:
    """파일 본문에서 검색용 키워드 요약 생성. Haiku 4.5 호출.

    Args:
        text: extracted_text — 보통 NasTextChunk content들을 join한 문자열.
        filename: 파일명. 프롬프트 컨텍스트 보강용.

    Returns:
        100~200자 한국어 키워드 요약. 실패/빈 응답 시 빈 문자열.
    """
    if not text or not text.strip():
        return ""

    last_error: Exception | None = None
    for attempt in range(RETRY_COUNT + 1):
        try:
            summary = await asyncio.to_thread(_call_haiku_sync, text, filename)
            if summary:
                return summary
            return ""
        except Exception as exc:  # noqa: BLE001 - caller가 skip 처리
            last_error = exc
            if attempt < RETRY_COUNT:
                logger.warning(
                    "요약 생성 실패 (%s, attempt %d/%d): %s — %.1fs 후 재시도",
                    filename,
                    attempt + 1,
                    RETRY_COUNT + 1,
                    exc,
                    RETRY_DELAY_SEC,
                )
                await asyncio.sleep(RETRY_DELAY_SEC)
                continue
            logger.warning(
                "요약 생성 최종 실패 (%s): %s",
                filename,
                exc,
            )
    # 모든 재시도 실패 → 빈 문자열 (caller가 skip)
    if last_error is not None:
        return ""
    return ""
