"""Phase C 세션 검수 전용 Pydantic 스키마 (T9).

엔드포인트 매핑 (Phase C):
- GET    /api/distribution/sessions             → SessionListItem 목록
- GET    /api/distribution/sessions/{id}        → SessionDetail
- PATCH  /api/distribution/messages/{id}        → MessageEditRequest → MessageItem
- POST   /api/distribution/sessions/{id}/approve → ApproveRequest
- POST   /api/distribution/sessions/{id}/reject  → RejectRequest
- POST   /api/distribution/sessions/{id}/send-now → SendNowResult

규칙:
- 자격증명/api_hash 절대 포함 X (스키마 정의 단계에서 차단).
- ORM 변환은 ``model_config = {"from_attributes": True}``.
- 기존 ``schemas/distribution.py`` 는 손대지 말 것 — Phase A/B 호환 보존.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 공통 타입
# ---------------------------------------------------------------------------

SessionStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "sending",
    "sent",
    "failed",
]

MessageStatus = Literal["queued", "sent", "failed", "skipped"]


# ---------------------------------------------------------------------------
# 목록 / 상세 응답
# ---------------------------------------------------------------------------


class SessionListItem(BaseModel):
    """세션 목록 1행. scenario/persona join 으로 라벨까지 채워서 전달."""

    id: UUID
    scenario_name: str
    sender_account_label: str
    receiver_account_label: str
    status: SessionStatus
    generated_at: datetime
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    scheduled_start: datetime | None = None
    message_count: int = Field(ge=0, description="해당 세션의 메시지 총 개수")
    llm_cost_usd: Decimal | None = None
    # 시나리오가 첨부 권장이면 True (T9 — 2026-05-26).
    scenario_attachment_required: bool = False

    model_config = ConfigDict(from_attributes=True)


class MessageItem(BaseModel):
    """세션 내 메시지 1개. 어드민 UI 검수 + 편집 화면에서 사용."""

    id: UUID
    order_index: int
    sender_account_label: str
    content: str
    edited_content: str | None = None
    user_edited: bool = False
    send_after_sec: int
    typing_sec: int
    status: MessageStatus
    sent_at: datetime | None = None
    telegram_message_id: str | None = None

    # 파일 첨부 (T9 — 2026-05-26).
    attachment_filename: str | None = None
    attachment_mime: str | None = None
    attachment_kind: str | None = None  # 'image' | 'document'
    attachment_caption: str | None = None
    # 다운로드/미리보기 URL — 라우터에서 채움. attachment_path 자체는 노출하지 않음.
    attachment_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SessionDetail(BaseModel):
    """세션 상세 응답 — 헤더 + 메시지 리스트."""

    session: SessionListItem
    messages: list[MessageItem]


# ---------------------------------------------------------------------------
# 요청 바디
# ---------------------------------------------------------------------------


class MessageEditRequest(BaseModel):
    """메시지 편집 요청.

    - edited_content: 본문 변경 (1~4096자, 비어있는 본문은 거부).
    - send_after_sec: 이전 메시지 송신 후 대기 초 (0 ~ 86400, 0~24시간).
    둘 중 하나는 반드시 제공되어야 함 (라우터에서 검증).
    """

    edited_content: str | None = Field(default=None, min_length=1, max_length=4096)
    send_after_sec: int | None = Field(default=None, ge=0, le=86400)


class ApproveRequest(BaseModel):
    """세션 승인 요청.

    scheduled_start 가 None 이면 즉시 송신 가능 상태.
    값이 있으면 워커가 해당 시각 이후에 픽업.
    """

    scheduled_start: datetime | None = None


class RejectRequest(BaseModel):
    """세션 거부 요청. reason 은 운영자 메모용 — 로그에만 남김."""

    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# 액션 응답
# ---------------------------------------------------------------------------


class SendNowResult(BaseModel):
    """즉시 송신 결과 요약."""

    session_id: UUID
    status: SessionStatus
    sent_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    error: str | None = None
