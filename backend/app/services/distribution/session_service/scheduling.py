"""예약 송신 스케줄링 (approve + scheduled_start).

원본 ``session_service.py`` 에서 분할. 동작 동일 (코드 verbatim 이동).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import (
    DistributionMessage,
    DistributionSession,
)

from ._common import logger


async def schedule_session_messages(
    db: AsyncSession,
    session: DistributionSession,
    *,
    scheduled_start: datetime,
) -> None:
    """세션 메시지마다 절대 송신 예정 시각(scheduled_send_at)을 계산·영속화.

    scheduled_send_at[i] = scheduled_start + sum(send_after_sec[0..i]).
    각 메시지의 send_after_sec 는 "직전 메시지 송신 후 대기 초" 이므로 누적합.
    워커가 ``send_state='pending' AND scheduled_send_at <= now()`` 로 due 판정.
    호출자가 commit 책임 (approve_session 트랜잭션 내에서 함께 commit).
    """
    msg_stmt = (
        select(DistributionMessage)
        .where(DistributionMessage.session_id == session.id)
        .order_by(DistributionMessage.order_index.asc())
    )
    messages = list((await db.execute(msg_stmt)).scalars())
    cumulative = 0
    for message in messages:
        cumulative += int(message.send_after_sec or 0)
        message.scheduled_send_at = scheduled_start + timedelta(seconds=cumulative)
        message.send_state = "pending"
        db.add(message)
    logger.info(
        "session scheduled — id=%s start=%s messages=%d",
        session.id,
        scheduled_start,
        len(messages),
    )
