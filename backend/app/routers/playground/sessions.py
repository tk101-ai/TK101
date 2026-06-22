"""세션 CRUD — 생성/목록/메시지/삭제/제목수정/Markdown export. + 본인 한도."""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.playground import PlaygroundMessage, PlaygroundSession
from app.models.user import User
from app.schemas.playground import (
    PlaygroundMessageOut,
    PlaygroundQuotaInfo,
    PlaygroundSessionCreate,
    PlaygroundSessionOut,
    PlaygroundSessionTitleUpdate,
)
from app.services.playground import create_session, list_sessions
from app.services.playground.usage_check import get_user_usage_summary

from ._common import fetch_session_or_404, make_subrouter

logger = logging.getLogger(__name__)

router: APIRouter = make_subrouter()


@router.post(
    "/sessions",
    response_model=PlaygroundSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    body: PlaygroundSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundSessionOut:
    row = await create_session(
        db,
        user_id=user.id,
        provider=body.provider,
        model=body.model,
        title=body.title,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
    )
    return PlaygroundSessionOut.model_validate(row)


@router.get("/sessions", response_model=list[PlaygroundSessionOut])
async def list_sessions_endpoint(
    q: str | None = Query(default=None, description="제목/메시지 내용 ILIKE 검색"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaygroundSessionOut]:
    """본인 세션 목록. q 가 있으면 title ILIKE 또는 messages.content ILIKE 매칭."""
    if not q:
        rows = await list_sessions(db, user_id=user.id)
        return [PlaygroundSessionOut.model_validate(r) for r in rows]

    pattern = f"%{q}%"
    # 메시지 내용에 매칭되는 세션 id subquery.
    msg_subq = (
        select(PlaygroundMessage.session_id)
        .where(PlaygroundMessage.content.ilike(pattern))
        .distinct()
    )
    stmt = (
        select(PlaygroundSession)
        .where(
            PlaygroundSession.user_id == user.id,
            (PlaygroundSession.title.ilike(pattern)) | (PlaygroundSession.id.in_(msg_subq)),
        )
        .order_by(PlaygroundSession.created_at.desc())
        .limit(50)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [PlaygroundSessionOut.model_validate(r) for r in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[PlaygroundMessageOut])
async def list_messages_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaygroundMessageOut]:
    session = await fetch_session_or_404(db, session_id, user)
    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session.id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [PlaygroundMessageOut.model_validate(r) for r in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    session = await fetch_session_or_404(db, session_id, user)
    await db.delete(session)
    await db.commit()


@router.patch("/sessions/{session_id}", response_model=PlaygroundSessionOut)
async def update_session_title_endpoint(
    session_id: uuid.UUID,
    body: PlaygroundSessionTitleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundSessionOut:
    """본인 세션 제목 수정."""
    session = await fetch_session_or_404(db, session_id, user)
    session.title = body.title
    await db.commit()
    await db.refresh(session)
    return PlaygroundSessionOut.model_validate(session)


@router.get("/sessions/{session_id}/export")
async def export_session_endpoint(
    session_id: uuid.UUID,
    format: Literal["md"] = Query(default="md"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """세션 메타 + 메시지 순서대로 Markdown 으로 내보내기."""
    session = await fetch_session_or_404(db, session_id, user)
    try:
        stmt = (
            select(PlaygroundMessage)
            .where(PlaygroundMessage.session_id == session.id)
            .order_by(PlaygroundMessage.created_at.asc())
        )
        messages = (await db.execute(stmt)).scalars().all()

        title = session.title or "(제목 없음)"
        lines: list[str] = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"- 모델: {session.provider}/{session.model}")
        created = (
            session.created_at.isoformat() if session.created_at else "unknown"
        )
        lines.append(f"- 생성: {created}")
        if session.system_prompt:
            lines.append(f"- System Prompt: {session.system_prompt}")
        lines.append("")
        lines.append("---")
        lines.append("")
        for msg in messages:
            if msg.role == "user":
                lines.append("## User")
            elif msg.role == "assistant":
                lines.append("## Assistant")
            else:
                lines.append(f"## {msg.role.capitalize()}")
            lines.append("")
            lines.append(msg.content or "")
            lines.append("")

        body_text = "\n".join(lines)
        safe_title = (
            "".join(c for c in title if c.isalnum() or c in ("-", "_"))
            or "session"
        )
        filename = f"{safe_title}.md"
        return Response(
            content=body_text.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\""
            },
        )
    except Exception as exc:  # noqa: BLE001 — 정확한 detail 노출 (500 generic 방지)
        logger.exception("export 실패 session_id=%s", session_id)
        raise HTTPException(
            status_code=500, detail=f"export 실패: {exc.__class__.__name__}: {exc}"
        ) from exc


@router.get("/me/quota", response_model=PlaygroundQuotaInfo)
async def get_my_quota_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundQuotaInfo:
    """본인 월 한도 + 이번 월 누적 사용량 + 잔여."""
    summary = await get_user_usage_summary(db, user.id)
    return PlaygroundQuotaInfo(**summary)
