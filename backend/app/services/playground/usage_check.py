"""사용자별 월 한도 체크 (T8 Playground 백엔드 확장 — 2026-05-19).

이번 월(``date_trunc('month', now())`` 이후) 의 누적 cost_usd 를 텍스트
(``playground_messages.cost_usd``) + 미디어(``playground_media.cost_usd``)
양쪽에서 합산. ``users.monthly_quota_usd`` 와 비교해서 초과면 402.

호출 순서:
- 라우터의 /chat, /image, /video 진입 시 맨 앞에서 ``check_quota_or_raise``.
- /me/quota 엔드포인트는 ``get_user_usage_summary`` 결과를 그대로 반환.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypedDict

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playground import PlaygroundMedia, PlaygroundMessage, PlaygroundSession
from app.models.user import User


class UsageSummary(TypedDict):
    monthly_quota_usd: Decimal
    current_usage_usd: Decimal
    remaining_usd: Decimal
    period_start: datetime
    period_end: datetime


def _month_bounds() -> tuple[datetime, datetime]:
    """이번 월의 시작 (UTC 1일 00:00) 과 끝 (다음 월 1일 00:00) 반환."""
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # 다음 월 1일.
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)
    return period_start, period_end


async def get_user_usage_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> UsageSummary:
    """이번 월 (UTC 기준) 의 누적 사용량 + 한도 + 잔여."""
    period_start, period_end = _month_bounds()

    # 사용자 한도.
    quota_stmt = select(User.monthly_quota_usd).where(User.id == user_id)
    quota_row = (await db.execute(quota_stmt)).scalar_one_or_none()
    quota = Decimal(quota_row) if quota_row is not None else Decimal("0")

    # 텍스트 사용량 (assistant 메시지의 cost_usd 합).
    text_stmt = (
        select(func.coalesce(func.sum(PlaygroundMessage.cost_usd), 0))
        .join(
            PlaygroundSession,
            PlaygroundSession.id == PlaygroundMessage.session_id,
        )
        .where(
            PlaygroundSession.user_id == user_id,
            PlaygroundMessage.created_at >= period_start,
            PlaygroundMessage.created_at < period_end,
            PlaygroundMessage.role == "assistant",
        )
    )
    text_cost = Decimal((await db.execute(text_stmt)).scalar() or 0)

    # 미디어 사용량 (성공한 task 만).
    media_stmt = select(
        func.coalesce(func.sum(PlaygroundMedia.cost_usd), 0)
    ).where(
        PlaygroundMedia.user_id == user_id,
        PlaygroundMedia.created_at >= period_start,
        PlaygroundMedia.created_at < period_end,
        PlaygroundMedia.status == "succeeded",
    )
    media_cost = Decimal((await db.execute(media_stmt)).scalar() or 0)

    current = (text_cost + media_cost).quantize(Decimal("0.000001"))
    remaining = (quota - current).quantize(Decimal("0.000001"))

    return UsageSummary(
        monthly_quota_usd=quota,
        current_usage_usd=current,
        remaining_usd=remaining,
        period_start=period_start,
        period_end=period_end,
    )


async def check_quota_or_raise(db: AsyncSession, user: User) -> UsageSummary:
    """한도 초과 시 HTTP 402 raise. 미초과면 summary 반환.

    사용처: /chat, /image, /video 진입 시 맨 앞.
    """
    summary = await get_user_usage_summary(db, user.id)
    if summary["current_usage_usd"] >= summary["monthly_quota_usd"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="사용량 한도 초과",
        )
    return summary


__all__ = [
    "UsageSummary",
    "get_user_usage_summary",
    "check_quota_or_raise",
]
