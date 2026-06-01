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
import os
from datetime import datetime, timedelta, timezone
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
# 텔레그램 미디어 캡션 최대 길이 (텍스트는 4096, 캡션은 1024).
# 초과 시 잘라서 첨부 보내고, 남은 본문은 별도 텍스트 메시지로 follow-up.
_CAPTION_MAX_LEN = 1024

# 워커 경로에서 실제 시간차 대기에 cap 없음 — None 전달.
# 단 단일 대기가 비현실적으로 길면 폴링 주기로 분할되므로, 여기서는 cap 미적용만 표현.

# 단일 메시지 송신 결과 (sent/failed). 호출자가 카운트·로그 집계.
_DELIVER_OK = "sent"
_DELIVER_FAIL = "failed"


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
        language=session.language,  # type: ignore[arg-type]
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
        send_state=message.send_state or "pending",  # type: ignore[arg-type]
        scheduled_send_at=message.scheduled_send_at,
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


# ---------------------------------------------------------------------------
# 타임라인 직접 편집 (메시지 추가/삭제) + 수동 세션 생성
# ---------------------------------------------------------------------------

# 타임라인 편집은 검수 대기 상태에서만 (승인/송신 후 변경 차단).
_EDITABLE_SESSION_STATUS = "pending"
# 수동 작성 세션이 참조할 숨김 시나리오 이름 (세션은 scenario_id NOT NULL).
_MANUAL_SCENARIO_NAME = "[수동 작성]"


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

    ValueError: 페르소나 미존재 / 발신=수신 동일.
    """
    if sender_persona_id == receiver_persona_id:
        raise ValueError("발신/수신 페르소나가 동일할 수 없습니다.")
    res = await db.execute(
        select(DistributionPersona.id).where(
            DistributionPersona.id.in_([sender_persona_id, receiver_persona_id])
        )
    )
    found = {row[0] for row in res.all()}
    for pid in (sender_persona_id, receiver_persona_id):
        if pid not in found:
            raise ValueError(f"페르소나 {pid} 가 존재하지 않습니다.")

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


# ---------------------------------------------------------------------------
# 예약 송신 스케줄링 (approve + scheduled_start)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 재사용 송신 헬퍼 (즉시 송신 + 워커 공용)
# ---------------------------------------------------------------------------


async def resolve_session_peers(
    sender: DistributionPersona,
    receiver: DistributionPersona,
    clients: dict[UUID, TelegramClient],
) -> dict[tuple[UUID, UUID], TelegramUser]:
    """양방향 peer entity 사전 해석 (contact import 포함). 즉시/워커 공용."""
    peer_cache: dict[tuple[UUID, UUID], TelegramUser] = {}
    for from_p, to_p in ((sender, receiver), (receiver, sender)):
        entity = await _resolve_peer(clients[from_p.id], to_p)
        peer_cache[(from_p.id, to_p.id)] = entity
    return peer_cache


def _parse_chat_id(raw: str):
    """그룹 chat 참조 정규화. 숫자(-100… 포함)면 int, 아니면 username/링크 문자열 그대로.

    Telethon get_entity 는 int id / @username / t.me 링크를 모두 허용한다.
    """
    text = (raw or "").strip()
    try:
        return int(text)
    except (TypeError, ValueError):
        return text


async def resolve_session_targets(
    session: DistributionSession,
    sender: DistributionPersona,
    receiver: DistributionPersona,
    clients: dict[UUID, TelegramClient],
) -> dict[UUID, object]:
    """발신 페르소나 id → 송신 타겟 엔티티.

    - session.group_chat_id 설정 시: 모든 발신자가 그 그룹(chat)으로 송신
      (각 클라이언트가 그룹 엔티티를 각자 resolve). → 3명 방.
    - 미설정 시: 기존 1:1 — 발신자는 상대 페르소나에게 DM (peer import 포함).
    """
    targets: dict[UUID, object] = {}
    if session.group_chat_id:
        chat_ref = _parse_chat_id(session.group_chat_id)
        for persona in (sender, receiver):
            targets[persona.id] = await clients[persona.id].get_entity(chat_ref)
        return targets
    for from_p, to_p in ((sender, receiver), (receiver, sender)):
        targets[from_p.id] = await _resolve_peer(clients[from_p.id], to_p)
    return targets


async def discover_group_dialogs(persona: DistributionPersona) -> list[dict]:
    """페르소나 계정이 참여 중인 그룹/슈퍼그룹 목록 (그룹 chat_id 찾기용).

    관리자가 텔레그램에서 3명 방을 만든 뒤, 그 방의 chat_id 를 UI 에서 고를 수
    있도록 해당 계정의 그룹 대화만 반환한다. 개인 DM 은 제외.
    """
    client = await _open_telethon_client(persona)
    try:
        out: list[dict] = []
        async for dialog in client.iter_dialogs():
            if getattr(dialog, "is_group", False):
                out.append(
                    {"chat_id": str(dialog.id), "title": dialog.name or "(제목 없음)"}
                )
        return out
    finally:
        try:
            await client.disconnect()
        except Exception:  # pragma: no cover — 정리 best-effort
            logger.warning("telethon client disconnect 실패 (무시)")


def _typing_action_for(message: DistributionMessage) -> str:
    """첨부 종류에 맞는 Telethon ChatAction 짧은 이름 반환."""
    if not message.attachment_path:
        return "typing"
    return "photo" if message.attachment_kind == "image" else "document"


async def _send_payload(
    client: TelegramClient,
    target_entity: TelegramUser,
    message: DistributionMessage,
):
    """첨부 유무에 따라 파일 또는 텍스트 송신. 송신된 메시지 객체 반환.

    캡션 1024자 초과분은 별도 텍스트로 follow-up.
    """
    if message.attachment_path:
        if not os.path.isfile(message.attachment_path):
            raise FileNotFoundError(
                f"첨부 파일이 존재하지 않습니다 ({message.attachment_path})"
            )
        raw_caption = (
            message.attachment_caption
            or message.edited_content
            or message.content
            or ""
        )
        caption = raw_caption[:_CAPTION_MAX_LEN]
        overflow = raw_caption[_CAPTION_MAX_LEN:]
        sent = await client.send_file(
            target_entity,
            message.attachment_path,
            caption=caption,
            force_document=(message.attachment_kind != "image"),
        )
        if overflow:
            await client.send_message(target_entity, overflow)
        return sent
    return await client.send_message(
        target_entity, message.edited_content or message.content
    )


async def _deliver_message(
    db: AsyncSession,
    *,
    client: TelegramClient,
    target_entity: TelegramUser,
    message: DistributionMessage,
    from_persona: DistributionPersona,
    cap_seconds: int | None,
) -> tuple[str, str | None]:
    """단일 메시지 1건 송신 (즉시/워커 공용 코어).

    cap_seconds:
        - 30 → 즉시 송신(UI 동기) 경로. send_after_sec/typing_sec 를 cap.
        - None → 워커 경로. 시간차는 이미 scheduled_send_at 으로 흡수되었으므로
          여기서 추가 대기는 하지 않고 typing 만 짧게.
    반환: (결과='sent'|'failed', error_summary | None). error_summary 는 실패 시
    사람이 읽을 요약 (자격증명 무관, 예외 타입+메시지만).
    message.status·send_log 를 기록. commit 은 호출자 책임 (배치 단위 제어).
    """
    if cap_seconds is not None:
        wait_sec = min(message.send_after_sec or 0, cap_seconds)
        if wait_sec > 0:
            await asyncio.sleep(wait_sec)
    typing_sec = min(message.typing_sec or 0, _TYPING_CAP_SEC)
    try:
        async with client.action(target_entity, _typing_action_for(message)):
            if typing_sec > 0:
                await asyncio.sleep(typing_sec)
        sent = await _send_payload(client, target_entity, message)
        message.status = "sent"
        message.send_state = "sent"  # status 와 동기화 (즉시·워커 경로 공통).
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
        logger.info(
            "message sent — id=%s from=%s tg_id=%s attach=%s",
            message.id,
            from_persona.account_label,
            sent.id,
            bool(message.attachment_path),
        )
        return _DELIVER_OK, None
    except (RPCError, FileNotFoundError, OSError, ValueError) as exc:
        # RPCError=텔레그램 거부 / FileNotFound·OSError=첨부 접근 실패 / ValueError=Telethon 검증.
        message.status = "failed"
        message.send_state = "failed"  # status 와 동기화 (즉시·워커 경로 공통).
        db.add(message)
        error_code = type(exc).__name__
        error_detail = str(exc)[:500]  # DB 컬럼 길이 보호 + 자격증명 미노출.
        db.add(
            DistributionSendLog(
                message_id=message.id,
                persona_id=from_persona.id,
                attempt=1,
                success=False,
                error_code=error_code,
                error_detail=error_detail,
            )
        )
        logger.warning(
            "message send failed — id=%s from=%s attach=%s err=%s detail=%s",
            message.id,
            from_persona.account_label,
            bool(message.attachment_path),
            error_code,
            error_detail,
        )
        return _DELIVER_FAIL, f"{error_code}: {error_detail}"


# ---------------------------------------------------------------------------
# 즉시 송신
# ---------------------------------------------------------------------------


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
