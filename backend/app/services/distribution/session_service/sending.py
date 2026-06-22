"""재사용 송신 헬퍼 (즉시 송신 + 워커 공용).

peer/target 해석, 그룹 대화 탐색, 단일 메시지 송신 코어.
원본 ``session_service.py`` 에서 분할. 동작 동일 (코드 verbatim 이동).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import User as TelegramUser

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionSendLog,
    DistributionSession,
)

from ._common import (
    _CAPTION_MAX_LEN,
    _DELIVER_FAIL,
    _DELIVER_OK,
    _TYPING_CAP_SEC,
    _open_telethon_client,
    _resolve_peer,
    logger,
)


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
