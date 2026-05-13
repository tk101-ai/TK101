"""Playground 세션/메시지 DB CRUD (T8 Phase 1).

라우터에서 호출하는 thin layer. 비즈니스 로직 (예: 세션 자동 제목 생성) 은
향후 Phase 에서 추가.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playground import PlaygroundMessage, PlaygroundSession


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider: str,
    model: str,
    title: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.7,
) -> PlaygroundSession:
    """빈 세션 1개 생성 후 commit."""
    row = PlaygroundSession(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        temperature=Decimal(str(temperature)),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_sessions(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 50
) -> list[PlaygroundSession]:
    """본인 세션 목록 (최신순). limit 기본 50건."""
    stmt = (
        select(PlaygroundSession)
        .where(PlaygroundSession.user_id == user_id)
        .order_by(PlaygroundSession.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def append_message(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    role: str,
    content: str,
    model: str | None = None,
    raw_request: dict | None = None,
) -> PlaygroundMessage:
    """메시지 1건 추가. 메트릭은 ``update_metrics`` 에서 채움."""
    row = PlaygroundMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        model=model,
        raw_request=raw_request,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_metrics(
    db: AsyncSession,
    *,
    message_id: uuid.UUID,
    content: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    latency_ms: int | None = None,
    raw_response: dict | None = None,
) -> PlaygroundMessage | None:
    """assistant 메시지 메트릭 백필.

    스트림 종료 후 라우터가 호출. content 가 주어지면 함께 갱신.
    """
    result = await db.execute(
        select(PlaygroundMessage).where(PlaygroundMessage.id == message_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if content is not None:
        row.content = content
    if input_tokens is not None:
        row.input_tokens = input_tokens
    if output_tokens is not None:
        row.output_tokens = output_tokens
    if cached_tokens is not None:
        row.cached_tokens = cached_tokens
    if reasoning_tokens is not None:
        row.reasoning_tokens = reasoning_tokens
    if latency_ms is not None:
        row.latency_ms = latency_ms
    # total_tokens 는 input+output+cached(read+create) 합으로 단순 계산.
    if input_tokens is not None or output_tokens is not None:
        i = input_tokens or 0
        o = output_tokens or 0
        c = cached_tokens or 0
        row.total_tokens = i + o + c
    if raw_response is not None:
        row.raw_response = raw_response
    await db.commit()
    await db.refresh(row)
    return row


def mask_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """raw_request 저장 직전 Authorization 등 시크릿 마스킹.

    bank_import attachments 마스킹 패턴을 따른다 (요구사항 G).
    얕은 복사 후 ``headers.Authorization`` / ``api_key`` 류만 치환.
    """
    masked = dict(payload)
    headers = masked.get("headers")
    if isinstance(headers, dict):
        new_headers = dict(headers)
        for key in list(new_headers.keys()):
            if key.lower() in {"authorization", "x-api-key", "anthropic-version"}:
                new_headers[key] = "***masked***"
        masked["headers"] = new_headers
    for k in ("api_key", "anthropic_api_key", "authorization"):
        if k in masked:
            masked[k] = "***masked***"
    return masked
