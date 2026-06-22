"""즉시 송신 (UI 동기 트리거).

원본 ``session_service.py`` 에서 분할. 동작 동일 (코드 verbatim 이동).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionSession,
)

from ._common import (
    _DELIVER_OK,
    _SEND_NOW_DELAY_CAP_SEC,
    _get_session,
    _open_telethon_client,
    logger,
)
from .sending import _deliver_message, resolve_session_targets


async def send_session_now(
    db: AsyncSession, session_id: UUID
) -> tuple[DistributionSession, int, int, str | None]:
    """세션을 동기로 즉시 송신.

    Returns:
        (session, sent_count, failed_count, first_error)

    Raises:
        ValueError: status 가 송신 가능 상태('approved' 또는 'pending'+자동승인은 X) 아님.
        LookupError: 세션 자체가 없음.

    송신 흐름은 ``live_test.run_test`` 의 후반부와 동일하지만 사용자 input()
    및 미리보기 print 단계가 제거됨. 자격증명/api_hash 는 절대 로깅 X
    (``_open_telethon_client`` 내부에서 decrypt → 메모리에만 존재).
    """
    session = await _get_session(db, session_id)
    if session is None:
        raise LookupError(f"세션 {session_id} 없음.")
    if session.status not in ("approved",):
        raise ValueError(
            f"송신 불가 — 현재 상태={session.status}. 'approved' 만 송신 가능."
        )

    # sender / receiver 페르소나 로드.
    persona_stmt = select(DistributionPersona).where(
        DistributionPersona.id.in_(
            [session.sender_persona_id, session.receiver_persona_id]
        )
    )
    personas = list((await db.execute(persona_stmt)).scalars())
    persona_by_id: dict[UUID, DistributionPersona] = {p.id: p for p in personas}

    sender = persona_by_id.get(session.sender_persona_id)
    receiver = persona_by_id.get(session.receiver_persona_id)
    if sender is None or receiver is None:
        raise ValueError("세션의 sender/receiver 페르소나가 DB 에 없습니다.")

    # 메시지 로드 (order_index 순).
    msg_stmt = (
        select(DistributionMessage)
        .where(DistributionMessage.session_id == session_id)
        .order_by(DistributionMessage.order_index.asc())
    )
    messages = list((await db.execute(msg_stmt)).scalars())
    if not messages:
        raise ValueError("세션에 송신할 메시지가 없습니다.")

    # status='sending' 전환 + commit (UI 다른 탭에서 진행 상태 확인 가능).
    session.status = "sending"
    db.add(session)
    await db.commit()

    sender_by_id = {sender.id: sender, receiver.id: receiver}
    sent_count = 0
    failed_count = 0
    # 첫 실패의 사람이 읽을 수 있는 요약 (UI 에 노출 — 디버깅).
    first_error: str | None = None
    clients: dict[UUID, TelegramClient] = {}
    # from_persona_id → 송신 타겟 엔티티 (그룹 모드면 모두 그룹, 아니면 상대 peer).
    targets: dict[UUID, object] = {}

    try:
        # 1) 두 페르소나의 Telethon client 오픈.
        for persona in (sender, receiver):
            clients[persona.id] = await _open_telethon_client(persona)
            logger.info(
                "telethon client opened — persona=%s", persona.account_label
            )

        # 2) 송신 타겟 해석 — group_chat_id 있으면 그룹, 없으면 1:1 상대 peer.
        targets = await resolve_session_targets(session, sender, receiver, clients)

        # 3) 메시지 순회 송신 (UI 동기 트리거이므로 cap=30 적용).
        for message in messages:
            if message.status == "sent":
                # 재시도 시 이미 송신된 건은 건너뜀.
                continue

            from_persona = sender_by_id.get(message.sender_persona_id)
            if from_persona is None:
                logger.warning(
                    "메시지 %s 의 sender_persona_id=%s 가 세션 참여자가 아님 — skip",
                    message.id,
                    message.sender_persona_id,
                )
                message.status = "skipped"
                db.add(message)
                continue

            target_entity = targets[from_persona.id]

            result, error_summary = await _deliver_message(
                db,
                client=clients[from_persona.id],
                target_entity=target_entity,
                message=message,
                from_persona=from_persona,
                cap_seconds=_SEND_NOW_DELAY_CAP_SEC,
            )
            if result == _DELIVER_OK:
                sent_count += 1
            else:
                failed_count += 1
                if first_error is None:
                    first_error = (
                        f"[메시지 #{message.order_index + 1}] {error_summary}"
                    )
            await db.commit()

        # 4) 세션 종료 상태 결정.
        if failed_count == 0:
            session.status = "sent"
        elif sent_count == 0:
            session.status = "failed"
        else:
            # 부분 성공 — 'sent' 로 두되 failed_count > 0 으로 UI 가 노출.
            session.status = "sent"
        session.completed_at = datetime.now(timezone.utc)
        db.add(session)
        await db.commit()
    except Exception:
        # 예외 전파 전에 status='failed' 로 마감 + commit.
        # 자격증명 마스킹: exception 메시지 자체는 logger.exception 이 남기되,
        # api_hash/api_id 는 _open_telethon_client 내부에서만 사용되므로 노출 경로 없음.
        logger.exception("send_session_now 예외 — session=%s", session_id)
        session.status = "failed"
        session.completed_at = datetime.now(timezone.utc)
        db.add(session)
        await db.commit()
        raise
    finally:
        for client in clients.values():
            try:
                await client.disconnect()
            except Exception:  # pragma: no cover — 정리 단계 best-effort
                logger.warning("telethon client disconnect 실패 (무시)")

    await db.refresh(session)
    return session, sent_count, failed_count, first_error
