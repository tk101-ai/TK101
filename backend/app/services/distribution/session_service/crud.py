"""세션 CRUD — 목록/상세, 메시지 편집·추가·삭제, 수동 세션 생성, 승인/거부.

원본 ``session_service.py`` 에서 분할. 동작 동일 (코드 verbatim 이동).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionScenario,
    DistributionSession,
)
from app.schemas.distribution_sessions import (
    MessageItem,
    SessionDetail,
    SessionListItem,
    SessionStatus,
)

from ._common import (
    _EDITABLE_SESSION_STATUS,
    _MANUAL_SCENARIO_NAME,
    _build_message_item,
    _build_session_list_item,
    _get_session,
    logger,
)
from .scheduling import schedule_session_messages


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


# ---------------------------------------------------------------------------
# 타임라인 직접 편집 (메시지 추가/삭제) + 수동 세션 생성
# ---------------------------------------------------------------------------


async def _get_or_create_manual_scenario(db: AsyncSession) -> DistributionScenario:
    """수동 세션용 숨김 시나리오 get-or-create. active=False 라 picker 에 안 보임."""
    res = await db.execute(
        select(DistributionScenario).where(
            DistributionScenario.name == _MANUAL_SCENARIO_NAME
        )
    )
    scenario = res.scalar_one_or_none()
    if scenario is not None:
        return scenario
    scenario = DistributionScenario(
        name=_MANUAL_SCENARIO_NAME,
        trigger_event="manual",
        sender_role="domestic_admin",
        receiver_role="vietnam_admin",
        beats=[],
        example_msgs=None,
        instruction=None,
        raw_text=None,
        language="ko",
        active=False,
    )
    db.add(scenario)
    await db.flush()
    return scenario


async def create_manual_session(
    db: AsyncSession,
    *,
    sender_persona_id: UUID,
    receiver_persona_id: UUID,
    language: str = "zh",
    group_chat_id: str | None = None,
) -> UUID:
    """사용자가 직접 작성할 빈 세션 생성 (메시지 0개, status='pending').

    ValueError: 계정 미존재 / 발신=수신 동일 / 비활성·미연동 계정.
    """
    if sender_persona_id == receiver_persona_id:
        raise ValueError("첫 발송 계정과 대화 상대가 동일할 수 없습니다.")
    res = await db.execute(
        select(DistributionPersona).where(
            DistributionPersona.id.in_([sender_persona_id, receiver_persona_id])
        )
    )
    accounts = list(res.scalars().all())
    by_id = {account.id: account for account in accounts}
    for pid in (sender_persona_id, receiver_persona_id):
        account = by_id.get(pid)
        if account is None:
            raise ValueError(f"텔레그램 계정 {pid} 가 존재하지 않습니다.")
        if not account.active:
            raise ValueError(f"{account.account_label}: 비활성 계정은 세션에 사용할 수 없습니다.")
        if not (account.session_path and account.telegram_user_id):
            raise ValueError(
                f"{account.account_label}: 텔레그램 로그인이 완료된 계정만 사용할 수 있습니다."
            )

    scenario = await _get_or_create_manual_scenario(db)
    session = DistributionSession(
        scenario_id=scenario.id,
        sender_persona_id=sender_persona_id,
        receiver_persona_id=receiver_persona_id,
        status="pending",
        language=("zh" if language == "zh" else "ko"),
        group_chat_id=group_chat_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info("manual session created — id=%s", session.id)
    return session.id


async def add_message(
    db: AsyncSession,
    session_id: UUID,
    *,
    sender: str,
    content: str,
    send_after_sec: int = 0,
    typing_sec: int = 3,
    position: int | None = None,
) -> MessageItem | None:
    """타임라인에 메시지 1건 추가. None=세션 없음.

    - 검수 대기(pending) 세션만 허용 (ValueError → 라우터 409).
    - sender: 'sender'=세션 발신자 / 'receiver'=세션 수신자 (side).
    - position 위치에 삽입(이후 order_index +1 shift). None 이면 맨 끝.
    """
    session = await _get_session(db, session_id)
    if session is None:
        return None
    if session.status != _EDITABLE_SESSION_STATUS:
        raise ValueError(
            f"'{session.status}' 상태 세션은 편집할 수 없습니다 (검수 대기만 가능)."
        )
    sender_persona_id = (
        session.receiver_persona_id
        if sender == "receiver"
        else session.sender_persona_id
    )

    msgs = list(
        (
            await db.execute(
                select(DistributionMessage)
                .where(DistributionMessage.session_id == session_id)
                .order_by(DistributionMessage.order_index.asc())
            )
        ).scalars()
    )
    n = len(msgs)
    pos = n if position is None else max(0, min(position, n))
    for m in msgs:
        if m.order_index >= pos:
            m.order_index += 1
            db.add(m)
    new_msg = DistributionMessage(
        session_id=session_id,
        order_index=pos,
        sender_persona_id=sender_persona_id,
        content=content,
        send_after_sec=send_after_sec,
        typing_sec=typing_sec,
        status="queued",
        send_state="pending",
    )
    db.add(new_msg)
    await db.commit()
    await db.refresh(new_msg)

    label = await db.scalar(
        select(DistributionPersona.account_label).where(
            DistributionPersona.id == sender_persona_id
        )
    )
    logger.info(
        "message added — session=%s pos=%s sender=%s", session_id, pos, label
    )
    return _build_message_item(message=new_msg, sender_label=label or "")


async def delete_message(db: AsyncSession, message_id: UUID) -> bool | None:
    """메시지 1건 삭제 + 잔여 메시지 order_index 재정렬. None=메시지 없음.

    검수 대기(pending) 세션만 허용 (ValueError → 라우터 409).
    """
    res = await db.execute(
        select(DistributionMessage).where(DistributionMessage.id == message_id)
    )
    msg = res.scalar_one_or_none()
    if msg is None:
        return None
    session = await _get_session(db, msg.session_id)
    if session is not None and session.status != _EDITABLE_SESSION_STATUS:
        raise ValueError(
            f"'{session.status}' 상태 세션의 메시지는 삭제할 수 없습니다 (검수 대기만 가능)."
        )
    session_id = msg.session_id
    await db.delete(msg)
    await db.flush()

    remaining = list(
        (
            await db.execute(
                select(DistributionMessage)
                .where(DistributionMessage.session_id == session_id)
                .order_by(DistributionMessage.order_index.asc())
            )
        ).scalars()
    )
    for idx, m in enumerate(remaining):
        if m.order_index != idx:
            m.order_index = idx
            db.add(m)
    await db.commit()
    logger.info("message deleted — id=%s session=%s", message_id, session_id)
    return True


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

    session.approved_by = user_id
    session.approved_at = datetime.now(timezone.utc)
    if scheduled_start is not None:
        # 예약 송신: status='scheduled' + 메시지별 절대 송신 시각 영속화.
        # 워커가 scheduled_start <= now() 인 세션을 픽업 → due 메시지 송신.
        session.status = "scheduled"
        session.scheduled_start = scheduled_start
        await schedule_session_messages(
            db, session, scheduled_start=scheduled_start
        )
    else:
        # 즉시 송신 대기 — 기존 'approved' 흐름 유지 (지금 송신 버튼 대상).
        session.status = "approved"

    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(
        "session approved — id=%s by=%s status=%s scheduled=%s",
        session.id,
        user_id,
        session.status,
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
