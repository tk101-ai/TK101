"""세션 검수/송신 서비스 (T9 Phase C).

흐름:
- list_sessions(status_filter, limit, offset) → 페이지네이션 목록 (scenario/persona join).
- get_session_detail(id) → 세션 + 모든 메시지 (sender label 채워서).
- update_message(message_id, edited_content) → user_edited=True, status 유지.
- approve_session(id, user_id, scheduled_start?) → status='approved' + approved_by/at 기록.
- reject_session(id, reason?) → status='rejected'.
- send_session_now(id) → 동기 송신 (Telethon 두 client 오픈 후 메시지 순회 송신).

송신 로직은 ``live_test.py`` 의 ``_open_telethon_client`` / ``_resolve_peer`` 를 그대로 재사용.
CLI 흐름과 차이는 단 하나 — UI 트리거이므로 사용자 input() 확인 단계가 없고,
시간차(``send_after_sec``)는 30초 cap 으로 제한 (UI 가 동기로 기다리므로 길게 잡을 수 없음).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import User as TelegramUser

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionScenario,
    DistributionSendLog,
    DistributionSession,
)
from app.schemas.distribution_sessions import (
    MessageItem,
    SessionDetail,
    SessionListItem,
    SessionStatus,
)
from app.services.distribution.live_test import (
    _open_telethon_client,
    _resolve_peer,
)

logger = logging.getLogger(__name__)


# UI 가 동기로 기다리는 송신 흐름이므로 메시지 간 대기 시간을 30초로 cap.
# 워커가 비동기로 처리하는 정식 송신 경로(별도) 에서는 이 값을 적용하지 않음.
_SEND_NOW_DELAY_CAP_SEC = 30
# 타이핑 인디케이터도 동일하게 짧게 cap (UX 차원에서 5초 이상이면 부자연).
_TYPING_CAP_SEC = 5


# ---------------------------------------------------------------------------
# 내부 헬퍼: ORM → API 변환
# ---------------------------------------------------------------------------


def _build_session_list_item(
    session: DistributionSession,
    *,
    scenario_name: str,
    sender_label: str,
    receiver_label: str,
    message_count: int,
    scenario_attachment_required: bool = False,
) -> SessionListItem:
    """세션 ORM + join 결과를 목록 응답 1행으로 변환."""
    return SessionListItem(
        id=session.id,
        scenario_name=scenario_name,
        sender_account_label=sender_label,
        receiver_account_label=receiver_label,
        status=session.status,  # type: ignore[arg-type]
        generated_at=session.generated_at,
        approved_at=session.approved_at,
        completed_at=session.completed_at,
        scheduled_start=session.scheduled_start,
        message_count=message_count,
        llm_cost_usd=session.llm_cost_usd,
        scenario_attachment_required=scenario_attachment_required,
    )


def _build_message_item(
    message: DistributionMessage, *, sender_label: str
) -> MessageItem:
    # 첨부가 있으면 라우터 다운로드 endpoint 로 URL 노출 (실제 파일경로는 응답에 X).
    attachment_url = (
        f"/api/distribution/messages/{message.id}/attachment"
        if message.attachment_path
        else None
    )
    return MessageItem(
        id=message.id,
        order_index=message.order_index,
        sender_account_label=sender_label,
        content=message.content,
        edited_content=message.edited_content,
        user_edited=message.user_edited,
        send_after_sec=message.send_after_sec,
        typing_sec=message.typing_sec,
        status=message.status,  # type: ignore[arg-type]
        sent_at=message.sent_at,
        telegram_message_id=message.telegram_message_id,
        attachment_filename=message.attachment_filename,
        attachment_mime=message.attachment_mime,
        attachment_kind=message.attachment_kind,
        attachment_caption=message.attachment_caption,
        attachment_url=attachment_url,
    )


async def serialize_message(
    db: AsyncSession, message: DistributionMessage
) -> MessageItem:
    """라우터 공용 — 단일 메시지 → MessageItem (sender label 채움)."""
    sender = (
        await db.execute(
            select(DistributionPersona.account_label).where(
                DistributionPersona.id == message.sender_persona_id
            )
        )
    ).scalar_one()
    return _build_message_item(message=message, sender_label=sender)


# ---------------------------------------------------------------------------
# 목록 / 상세
# ---------------------------------------------------------------------------


async def list_sessions(
    db: AsyncSession,
    *,
    status_filter: SessionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SessionListItem]:
    """세션 목록 페이지네이션.

    Join 으로 scenario_name / sender·receiver label 까지 한 번에 가져옴.
    message_count 는 서브쿼리 COUNT(*).
    """
    sender = DistributionPersona.__table__.alias("sender_persona")
    receiver = DistributionPersona.__table__.alias("receiver_persona")

    # 메시지 카운트 서브쿼리.
    msg_count_subq = (
        select(
            DistributionMessage.session_id,
            func.count(DistributionMessage.id).label("msg_count"),
        )
        .group_by(DistributionMessage.session_id)
        .subquery()
    )

    stmt = (
        select(
            DistributionSession,
            DistributionScenario.name,
            DistributionScenario.attachment_required,
            sender.c.account_label,
            receiver.c.account_label,
            func.coalesce(msg_count_subq.c.msg_count, 0),
        )
        .join(
            DistributionScenario,
            DistributionScenario.id == DistributionSession.scenario_id,
        )
        .join(sender, sender.c.id == DistributionSession.sender_persona_id)
        .join(receiver, receiver.c.id == DistributionSession.receiver_persona_id)
        .outerjoin(
            msg_count_subq,
            msg_count_subq.c.session_id == DistributionSession.id,
        )
        .order_by(DistributionSession.generated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if status_filter is not None:
        stmt = stmt.where(DistributionSession.status == status_filter)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        _build_session_list_item(
            session=session,
            scenario_name=scenario_name,
            sender_label=sender_label,
            receiver_label=receiver_label,
            message_count=int(msg_count or 0),
            scenario_attachment_required=bool(attachment_required),
        )
        for session, scenario_name, attachment_required, sender_label, receiver_label, msg_count in rows
    ]


async def get_session_detail(
    db: AsyncSession, session_id: UUID
) -> SessionDetail | None:
    """세션 상세 — 헤더 (목록과 동일 모양) + 메시지 리스트.

    메시지의 sender_persona_id 를 label 로 풀어서 응답에 채움.
    """
    sender = DistributionPersona.__table__.alias("sender_persona")
    receiver = DistributionPersona.__table__.alias("receiver_persona")

    msg_count_subq = (
        select(func.count(DistributionMessage.id))
        .where(DistributionMessage.session_id == session_id)
        .scalar_subquery()
    )

    header_stmt = (
        select(
            DistributionSession,
            DistributionScenario.name,
            DistributionScenario.attachment_required,
            sender.c.account_label,
            receiver.c.account_label,
            msg_count_subq,
        )
        .join(
            DistributionScenario,
            DistributionScenario.id == DistributionSession.scenario_id,
        )
        .join(sender, sender.c.id == DistributionSession.sender_persona_id)
        .join(receiver, receiver.c.id == DistributionSession.receiver_persona_id)
        .where(DistributionSession.id == session_id)
    )
    header_row = (await db.execute(header_stmt)).first()
    if header_row is None:
        return None

    (
        session_obj,
        scenario_name,
        attachment_required,
        sender_label,
        receiver_label,
        message_count,
    ) = header_row

    # 메시지 + sender label join.
    msg_stmt = (
        select(DistributionMessage, DistributionPersona.account_label)
        .join(
            DistributionPersona,
            DistributionPersona.id == DistributionMessage.sender_persona_id,
        )
        .where(DistributionMessage.session_id == session_id)
        .order_by(DistributionMessage.order_index.asc())
    )
    msg_rows = (await db.execute(msg_stmt)).all()

    messages = [
        _build_message_item(message=m, sender_label=label) for m, label in msg_rows
    ]

    header = _build_session_list_item(
        session=session_obj,
        scenario_name=scenario_name,
        sender_label=sender_label,
        receiver_label=receiver_label,
        message_count=int(message_count or 0),
        scenario_attachment_required=bool(attachment_required),
    )
    return SessionDetail(session=header, messages=messages)


# ---------------------------------------------------------------------------
# 편집 / 승인 / 거부
# ---------------------------------------------------------------------------


async def update_message(
    db: AsyncSession,
    message_id: UUID,
    *,
    edited_content: str | None = None,
    send_after_sec: int | None = None,
) -> MessageItem | None:
    """메시지 편집 — 본문 또는 송신 텀 갱신.

    - ``edited_content`` 제공 → user_edited=True.
    - ``send_after_sec`` 제공 → 텀만 변경 (user_edited 갱신 X).
    - 둘 다 None 이면 ValueError → 라우터 422.
    - status='sent' 면 ValueError → 라우터 422.
    """
    if edited_content is None and send_after_sec is None:
        raise ValueError(
            "edited_content / send_after_sec 중 하나는 반드시 제공해야 합니다."
        )

    result = await db.execute(
        select(DistributionMessage, DistributionPersona.account_label)
        .join(
            DistributionPersona,
            DistributionPersona.id == DistributionMessage.sender_persona_id,
        )
        .where(DistributionMessage.id == message_id)
    )
    row = result.first()
    if row is None:
        return None

    message, sender_label = row
    if message.status == "sent":
        # 라우터가 422 로 변환. 비즈니스 룰 위반.
        raise ValueError("이미 송신된 메시지는 편집할 수 없습니다.")

    if edited_content is not None:
        message.edited_content = edited_content
        message.user_edited = True
    if send_after_sec is not None:
        message.send_after_sec = send_after_sec

    db.add(message)
    await db.commit()
    await db.refresh(message)

    logger.info(
        "message updated — id=%s session=%s content=%s timing=%s",
        message.id,
        message.session_id,
        "yes" if edited_content is not None else "no",
        send_after_sec if send_after_sec is not None else "no",
    )
    return _build_message_item(message=message, sender_label=sender_label)


async def approve_session(
    db: AsyncSession,
    session_id: UUID,
    *,
    user_id: UUID,
    scheduled_start: datetime | None = None,
) -> DistributionSession | None:
    """세션 승인. status='pending' 만 승인 가능. 다른 상태면 ValueError."""
    session = await _get_session(db, session_id)
    if session is None:
        return None
    if session.status != "pending":
        raise ValueError(
            f"승인 불가 — 현재 상태={session.status}. 'pending' 만 승인 가능."
        )

    session.status = "approved"
    session.approved_by = user_id
    session.approved_at = datetime.now(timezone.utc)
    if scheduled_start is not None:
        session.scheduled_start = scheduled_start

    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(
        "session approved — id=%s by=%s scheduled=%s",
        session.id,
        user_id,
        scheduled_start,
    )
    return session


async def reject_session(
    db: AsyncSession,
    session_id: UUID,
    *,
    reason: str | None = None,
) -> DistributionSession | None:
    """세션 거부. status='pending' 만 거부 가능."""
    session = await _get_session(db, session_id)
    if session is None:
        return None
    if session.status != "pending":
        raise ValueError(
            f"거부 불가 — 현재 상태={session.status}. 'pending' 만 거부 가능."
        )

    session.status = "rejected"
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(
        "session rejected — id=%s reason=%s",
        session.id,
        (reason or "")[:100],
    )
    return session


# ---------------------------------------------------------------------------
# 즉시 송신
# ---------------------------------------------------------------------------


async def send_session_now(
    db: AsyncSession, session_id: UUID
) -> tuple[DistributionSession, int, int]:
    """세션을 동기로 즉시 송신.

    Returns:
        (session, sent_count, failed_count)

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
    clients: dict[UUID, TelegramClient] = {}
    # (from_persona_id, to_persona_id) → 텔레그램 User entity.
    peer_cache: dict[tuple[UUID, UUID], TelegramUser] = {}

    try:
        # 1) 두 페르소나의 Telethon client 오픈.
        for persona in (sender, receiver):
            clients[persona.id] = await _open_telethon_client(persona)
            logger.info(
                "telethon client opened — persona=%s", persona.account_label
            )

        # 2) 양방향 peer entity 해석 (contact import 포함).
        for from_p, to_p in ((sender, receiver), (receiver, sender)):
            entity = await _resolve_peer(clients[from_p.id], to_p)
            peer_cache[(from_p.id, to_p.id)] = entity

        # 3) 메시지 순회 송신.
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

            to_persona = (
                receiver if from_persona.id == sender.id else sender
            )
            target_entity = peer_cache[(from_persona.id, to_persona.id)]

            # 시간차 대기 (UI 동기 트리거이므로 cap 적용).
            wait_sec = min(message.send_after_sec or 0, _SEND_NOW_DELAY_CAP_SEC)
            if wait_sec > 0:
                await asyncio.sleep(wait_sec)

            client = clients[from_persona.id]
            try:
                # 타이핑 인디케이터 — 짧게. 첨부가 있으면 'upload_photo'/'upload_document'.
                typing_action = "typing"
                if message.attachment_path:
                    typing_action = (
                        "upload_photo"
                        if message.attachment_kind == "image"
                        else "upload_document"
                    )
                async with client.action(target_entity, typing_action):
                    await asyncio.sleep(min(message.typing_sec or 0, _TYPING_CAP_SEC))

                if message.attachment_path:
                    # 파일 첨부 송신. 문서류는 force_document=True 로 미리보기 없이 첨부.
                    # 캡션 우선순위: attachment_caption > edited_content > content.
                    caption = (
                        message.attachment_caption
                        or message.edited_content
                        or message.content
                        or ""
                    )
                    sent = await client.send_file(
                        target_entity,
                        message.attachment_path,
                        caption=caption,
                        force_document=(message.attachment_kind != "image"),
                        file_name=message.attachment_filename or None,
                    )
                else:
                    sent = await client.send_message(
                        target_entity,
                        message.edited_content or message.content,
                    )
                message.status = "sent"
                message.sent_at = datetime.now(timezone.utc)
                message.telegram_message_id = str(sent.id)
                db.add(message)
                db.add(
                    DistributionSendLog(
                        message_id=message.id,
                        persona_id=from_persona.id,
                        attempt=1,
                        success=True,
                    )
                )
                sent_count += 1
                logger.info(
                    "message sent — id=%s from=%s to=%s tg_id=%s",
                    message.id,
                    from_persona.account_label,
                    to_persona.account_label,
                    sent.id,
                )
            except RPCError as exc:
                message.status = "failed"
                db.add(message)
                db.add(
                    DistributionSendLog(
                        message_id=message.id,
                        persona_id=from_persona.id,
                        attempt=1,
                        success=False,
                        error_code=type(exc).__name__,
                        error_detail=str(exc),
                    )
                )
                failed_count += 1
                # 자격증명/api_hash 는 절대 로깅 X — RPCError 타입+메시지만.
                logger.warning(
                    "message send failed — id=%s from=%s err=%s",
                    message.id,
                    from_persona.account_label,
                    type(exc).__name__,
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
    return session, sent_count, failed_count


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _get_session(
    db: AsyncSession, session_id: UUID
) -> DistributionSession | None:
    result = await db.execute(
        select(DistributionSession).where(DistributionSession.id == session_id)
    )
    return result.scalar_one_or_none()
