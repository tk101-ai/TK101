"""예약 송신 백그라운드 워커 (T9 Priority 1 — 2026-05-27).

목적:
- 승인 + 예약(scheduled_start) 된 세션을 실시간으로 자동 송신한다.
- 즉시 송신(send_session_now)과 달리 30초 cap 이 없고, 메시지별
  scheduled_send_at 절대 시각을 honor 한다.
- 앱 재시작에도 안전하며, 동시성/재시작 환경에서 메시지를 중복 송신하지 않는다.

동작:
1. ``distribution_worker_poll_sec`` 마다 poll.
2. status in ('scheduled','sending') AND scheduled_start <= now() 인 세션 선택.
3. 각 세션에서 due (scheduled_send_at <= now() AND send_state='pending') 메시지를
   원자적 UPDATE ... RETURNING 으로 'sending' 으로 claim (중복 송신 차단).
4. 해당 세션의 Telethon client 2개를 batch 단위로 1번만 오픈 → due 메시지 송신.
5. send_state='sent'/'failed' + sent_at 기록.
6. 세션의 모든 메시지가 terminal 이면 status='sent' (실패 있으면 'failed') 마감.

중복 송신 방지 (No-Double-Send):
- claim 은 단일 SQL ``UPDATE ... WHERE send_state='pending' RETURNING id`` 로 수행.
  Postgres row-level lock + 조건부 UPDATE 이므로 동시에 두 워커/두 poll 사이클이
  같은 메시지를 잡으려 해도 한쪽만 성공 (나머지는 RETURNING 비어있음).
- claim 후 즉시 commit 하여 'sending' 상태를 영속화 → 송신 직전 크래시가 나도
  재시작 후 'sending' 으로 남아 자동 재송신되지 않음 (수동 점검 대상).

재시작 안전 (Restart-Safe):
- 모든 due 판정·상태는 DB 에 영속 (scheduled_send_at / send_state).
- 메모리 타이머가 아니므로 프로세스가 죽어도 다음 부팅 시 due 메시지를 다시 픽업.
- 'sent' 메시지는 send_state='sent' 라 다시 claim 되지 않음.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient

from app.config import settings
from app.database import async_session
from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionSession,
)
from app.services.distribution.session_service import (
    _DELIVER_OK,
    _deliver_message,
    _open_telethon_client,
    resolve_session_targets,
)

logger = logging.getLogger(__name__)

# 워커가 픽업하는 세션 상태 — 예약됨 + 진행중(재시작 복구).
_PICKUP_STATUSES = ("scheduled", "sending")
# 메시지 terminal 상태 (더 이상 송신 시도 안 함).
_TERMINAL_MESSAGE_STATES = ("sent", "failed", "skipped")


async def run_send_worker(stop_event: asyncio.Event) -> None:
    """워커 메인 루프. ``stop_event`` 가 set 될 때까지 poll.

    한 사이클의 예외는 루프를 죽이지 않고 다음 사이클로 넘어간다.
    """
    poll_sec = max(int(settings.distribution_worker_poll_sec or 15), 1)
    logger.info("distribution send worker started — poll=%ds", poll_sec)
    while not stop_event.is_set():
        try:
            await _poll_once()
        except Exception:  # pragma: no cover — 어떤 예외도 루프를 죽이지 않음.
            logger.exception("send worker poll 사이클 예외 (무시하고 계속)")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_sec)
        except asyncio.TimeoutError:
            pass
    logger.info("distribution send worker stopped")


async def _poll_once() -> None:
    """due 세션을 찾아 각각 처리. 세션 단위 독립 트랜잭션/세션."""
    async with async_session() as db:
        session_ids = await _find_due_session_ids(db)
    for session_id in session_ids:
        try:
            async with async_session() as db:
                await _process_session(db, session_id)
        except Exception:
            logger.exception("세션 처리 예외 — session=%s (다음 세션 계속)", session_id)


async def _find_due_session_ids(db: AsyncSession) -> list[UUID]:
    """status in (scheduled,sending) AND scheduled_start <= now() 인 세션 id."""
    stmt = (
        select(DistributionSession.id)
        .where(DistributionSession.status.in_(_PICKUP_STATUSES))
        .where(DistributionSession.scheduled_start.isnot(None))
        .where(DistributionSession.scheduled_start <= func.now())
        .order_by(DistributionSession.scheduled_start.asc())
    )
    return list((await db.execute(stmt)).scalars())


async def _claim_due_messages(
    db: AsyncSession, session_id: UUID
) -> list[DistributionMessage]:
    """due 메시지를 원자적으로 'sending' claim 후 ORM 객체로 반환.

    UPDATE ... WHERE send_state='pending' AND scheduled_send_at <= now() RETURNING id.
    Postgres 조건부 UPDATE 라 동시 claim 시 한쪽만 성공 → 중복 송신 차단.
    """
    claim_stmt = (
        update(DistributionMessage)
        .where(DistributionMessage.session_id == session_id)
        .where(DistributionMessage.send_state == "pending")
        .where(DistributionMessage.scheduled_send_at.isnot(None))
        .where(DistributionMessage.scheduled_send_at <= func.now())
        .values(send_state="sending")
        .returning(DistributionMessage.id)
    )
    claimed_ids = list((await db.execute(claim_stmt)).scalars())
    await db.commit()
    if not claimed_ids:
        return []
    rows = (
        await db.execute(
            select(DistributionMessage)
            .where(DistributionMessage.id.in_(claimed_ids))
            .order_by(DistributionMessage.order_index.asc())
        )
    ).scalars()
    return list(rows)


async def _process_session(db: AsyncSession, session_id: UUID) -> None:
    """단일 세션의 due 메시지 batch 송신."""
    claimed = await _claim_due_messages(db, session_id)
    if not claimed:
        # due 메시지 없음 — 단, 모든 메시지가 terminal 이면 세션 마감 시도.
        await _finalize_if_complete(db, session_id)
        return

    session = (
        await db.execute(
            select(DistributionSession).where(DistributionSession.id == session_id)
        )
    ).scalar_one_or_none()
    if session is None:
        return
    personas = await _load_personas(db, session)
    if personas is None:
        await _mark_claimed_failed(db, claimed, reason="페르소나 누락")
        return
    sender, receiver = personas

    if session.status != "sending":
        session.status = "sending"
        db.add(session)
        await db.commit()

    await _send_claimed_batch(db, session, sender, receiver, claimed)
    await _finalize_if_complete(db, session_id)


async def _load_personas(
    db: AsyncSession, session: DistributionSession
) -> tuple[DistributionPersona, DistributionPersona] | None:
    """세션의 sender/receiver 페르소나 로드. 누락 시 None."""
    rows = list(
        (
            await db.execute(
                select(DistributionPersona).where(
                    DistributionPersona.id.in_(
                        [session.sender_persona_id, session.receiver_persona_id]
                    )
                )
            )
        ).scalars()
    )
    by_id = {p.id: p for p in rows}
    sender = by_id.get(session.sender_persona_id)
    receiver = by_id.get(session.receiver_persona_id)
    if sender is None or receiver is None:
        return None
    return sender, receiver


async def _send_claimed_batch(
    db: AsyncSession,
    session: DistributionSession,
    sender: DistributionPersona,
    receiver: DistributionPersona,
    claimed: list[DistributionMessage],
) -> None:
    """claim 된 메시지를 batch 단위로 송신. client 는 1번만 오픈 후 재사용."""
    clients: dict[UUID, TelegramClient] = {}
    sender_by_id = {sender.id: sender, receiver.id: receiver}
    try:
        for persona in (sender, receiver):
            clients[persona.id] = await _open_telethon_client(persona)
        targets = await resolve_session_targets(session, sender, receiver, clients)
        for message in claimed:
            await _deliver_one(db, message, sender_by_id, targets, clients)
    except Exception:
        # client 오픈/peer 해석 단계 실패 — claim 된 메시지를 failed 로 마감.
        logger.exception(
            "batch 송신 준비 실패 — session=%s (claim 메시지 failed 처리)",
            session.id,
        )
        await _mark_claimed_failed(db, claimed, reason="클라이언트/피어 해석 실패")
    finally:
        for client in clients.values():
            try:
                await client.disconnect()
            except Exception:  # pragma: no cover — best-effort 정리.
                logger.warning("telethon client disconnect 실패 (무시)")


async def _deliver_one(
    db: AsyncSession,
    message: DistributionMessage,
    sender_by_id: dict[UUID, DistributionPersona],
    targets: dict,
    clients: dict[UUID, TelegramClient],
) -> None:
    """단일 claim 메시지 송신 → send_state 갱신. 실패해도 다음 메시지 계속."""
    from_persona = sender_by_id.get(message.sender_persona_id)
    if from_persona is None:
        message.send_state = "skipped"
        message.status = "skipped"
        db.add(message)
        await db.commit()
        return
    # 발신 페르소나별 타겟(그룹 모드면 그룹, 아니면 상대 peer).
    target_entity = targets[from_persona.id]
    result, _err = await _deliver_message(
        db,
        client=clients[from_persona.id],
        target_entity=target_entity,
        message=message,
        from_persona=from_persona,
        cap_seconds=None,  # 워커는 cap 없음 — 시간차는 scheduled_send_at 으로 흡수.
    )
    message.send_state = "sent" if result == _DELIVER_OK else "failed"
    db.add(message)
    await db.commit()


async def _mark_claimed_failed(
    db: AsyncSession, claimed: list[DistributionMessage], *, reason: str
) -> None:
    """준비 단계 실패 시 claim 된 메시지를 failed 로 마감 (sending 잔류 방지)."""
    for message in claimed:
        message.send_state = "failed"
        message.status = "failed"
        db.add(message)
    await db.commit()
    logger.warning(
        "claim 메시지 %d건 failed 처리 — reason=%s", len(claimed), reason
    )


async def _finalize_if_complete(db: AsyncSession, session_id: UUID) -> None:
    """세션의 모든 메시지가 terminal 이면 status 마감.

    실패 1건이라도 있으면 'failed', 전부 성공이면 'sent'.
    아직 pending/sending 이 남아있으면 아무 것도 안 함 (다음 poll 에서 처리).
    """
    states = list(
        (
            await db.execute(
                select(DistributionMessage.send_state).where(
                    DistributionMessage.session_id == session_id
                )
            )
        ).scalars()
    )
    if not states or any(s not in _TERMINAL_MESSAGE_STATES for s in states):
        return
    session = (
        await db.execute(
            select(DistributionSession).where(DistributionSession.id == session_id)
        )
    ).scalar_one_or_none()
    if session is None or session.status in ("sent", "failed"):
        return
    session.status = "failed" if "failed" in states else "sent"
    session.completed_at = datetime.now(timezone.utc)
    db.add(session)
    await db.commit()
    logger.info(
        "session finalized — id=%s status=%s messages=%d",
        session_id,
        session.status,
        len(states),
    )
