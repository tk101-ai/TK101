"""AI Playground Pydantic 스키마 (T8 PRD Phase 1).

엔드포인트 매핑:
- GET  /api/playground/providers          → list[PlaygroundProviderMeta]
- POST /api/playground/sessions           → PlaygroundSessionOut
- GET  /api/playground/sessions           → list[PlaygroundSessionOut]
- GET  /api/playground/sessions/{id}/...  → list[PlaygroundMessageOut]
- POST /api/playground/chat (SSE)         → text/event-stream
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Provider / Model 메타 — UI 변형 chip 노출용
# ---------------------------------------------------------------------------


class PlaygroundModelChip(BaseModel):
    """단일 모델 변형 chip.

    key:   API 호출 시 사용할 정확한 모델 ID (예: claude-opus-4-7).
    label: UI 표시명 (예: "Opus 4.7").
    badge: 옵션 배지 텍스트 (예: "1M", "최신"). 없으면 None.
    """

    key: str
    label: str
    badge: str | None = None


class PlaygroundProviderMeta(BaseModel):
    """Provider 카드 1개 + 그 안의 변형 chip 목록."""

    provider_key: str
    provider_label: str
    models: list[PlaygroundModelChip]


# ---------------------------------------------------------------------------
# 채팅 요청 / 세션 / 메시지
# ---------------------------------------------------------------------------


class PlaygroundChatRequest(BaseModel):
    """POST /api/playground/chat 요청 본문 (SSE 스트리밍)."""

    # session_id 가 None 이면 라우터가 새 세션을 생성.
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=200_000, description="사용자 메시지")
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    # Anthropic Messages API 허용 범위 (0.0 ~ 1.0). UI 에서 더 넓힐 일 없음.
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)


class PlaygroundSessionCreate(BaseModel):
    """POST /api/playground/sessions 요청 본문 — 빈 세션 생성용."""

    title: str | None = Field(default=None, max_length=200)
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)


class PlaygroundSessionOut(BaseModel):
    """세션 조회/생성 응답."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    provider: str
    model: str
    system_prompt: str | None
    temperature: Decimal
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PlaygroundMessageOut(BaseModel):
    """메시지 조회 응답. 메트릭은 assistant 메시지에서만 채워짐."""

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cached_tokens: int | None
    total_tokens: int | None
    latency_ms: int | None
    model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
