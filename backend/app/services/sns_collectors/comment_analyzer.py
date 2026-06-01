"""SNS 게시물 댓글 AI 분석/요약 (Claude Haiku).

수집된 댓글(social_post_comments)을 모아 게시물 단위로 한국어 분석 요약을 생성한다.
- 전반적 반응(긍/부정/중립 경향), 주요 주제·키워드, 자주 나온 의견,
  눈에 띄는 댓글, 마케팅 시사점.
- 마케팅1팀 댓글 분석 요구사항(T4) 대응.

비용: Haiku 4.5, 게시물당 1회 단발 호출. 입력은 길이 cap.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
# 입력 댓글 합산 길이 cap (토큰/비용 보호). 초과분은 잘림.
MAX_INPUT_CHARS = 24_000
MAX_OUTPUT_TOKENS = 900

SYSTEM_PROMPT = (
    "당신은 소셜미디어 댓글 분석 전문가입니다. 주어진 게시물 댓글들을 분석해 "
    "마케팅 담당자가 한눈에 파악할 수 있는 한국어 요약을 작성합니다. "
    "다음 항목을 간결한 markdown 으로 구성하세요: "
    "1) 전반적 반응(긍정/부정/중립 경향), 2) 주요 주제·키워드, "
    "3) 자주 나온 의견/요청, 4) 눈에 띄는 댓글 2~3개(원문 인용), "
    "5) 마케팅 시사점/개선 제안. 댓글에 없는 내용을 지어내지 마세요."
)


def _build_anthropic_client() -> Any:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 미설정 — 댓글 분석 사용 불가.")
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(f"anthropic SDK 미설치: {exc}") from exc
    return Anthropic(api_key=settings.anthropic_api_key)


def _join_comments(comments: list[str]) -> str:
    lines: list[str] = []
    total = 0
    for c in comments:
        text = (c or "").strip()
        if not text:
            continue
        line = f"- {text}"
        if total + len(line) > MAX_INPUT_CHARS:
            lines.append("…(이하 생략)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def _call_haiku_sync(post_title: str, joined: str, comment_count: int) -> str:
    client = _build_anthropic_client()
    user_content = (
        f"게시물 제목/본문: {post_title or '(제목 없음)'}\n"
        f"수집된 댓글 수: {comment_count}개\n\n"
        f"[댓글 목록]\n{joined}\n\n"
        f"→ 위 항목 구성대로 한국어 분석 요약:"
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
    return "".join(parts).strip()


async def analyze_comments(
    *, post_title: str, comments: list[str], comment_count: int
) -> str:
    """댓글 목록 → 한국어 분석 요약. 빈 댓글이면 ValueError.

    blocking Anthropic 호출이라 to_thread 로 이벤트 루프 분리.
    """
    joined = _join_comments(comments)
    if not joined:
        raise ValueError("분석할 댓글 본문이 없습니다.")
    summary = await asyncio.to_thread(
        _call_haiku_sync, post_title, joined, comment_count
    )
    return summary or "(요약 생성 실패 — 빈 응답)"
