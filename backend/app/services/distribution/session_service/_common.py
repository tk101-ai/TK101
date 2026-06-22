"""세션 서비스 공용 — 상수 / ORM→API 변환 헬퍼 / 세션 조회.

원본 ``session_service.py`` 에서 분할. 동작 동일 (코드 verbatim 이동).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionSession,
)
from app.schemas.distribution_sessions import (
    MessageItem,
    SessionListItem,
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

# 타임라인 편집은 검수 대기 상태에서만 (승인/송신 후 변경 차단).
_EDITABLE_SESSION_STATUS = "pending"
# 수동 작성 세션이 참조할 숨김 시나리오 이름 (세션은 scenario_id NOT NULL).
_MANUAL_SCENARIO_NAME = "[수동 작성]"


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
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _get_session(
    db: AsyncSession, session_id: UUID
) -> DistributionSession | None:
    result = await db.execute(
        select(DistributionSession).where(DistributionSession.id == session_id)
    )
    return result.scalar_one_or_none()
