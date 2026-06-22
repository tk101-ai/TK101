"""미디어 갤러리 — 본인 미디어 목록 + 파일 서빙."""
from __future__ import annotations

import os
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.playground import PlaygroundMedia
from app.models.user import User
from app.schemas.playground import PlaygroundMediaOut

from ._common import make_subrouter

router: APIRouter = make_subrouter()


@router.get("/media", response_model=list[PlaygroundMediaOut])
async def list_my_media(
    kind: Literal["image", "video"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaygroundMediaOut]:
    """본인이 만든 미디어 목록 (최신순). kind 로 필터."""
    stmt = (
        select(PlaygroundMedia)
        .where(PlaygroundMedia.user_id == user.id)
        .order_by(desc(PlaygroundMedia.created_at))
        .limit(limit)
    )
    if kind:
        stmt = stmt.where(PlaygroundMedia.media_type == kind)
    rows = (await db.execute(stmt)).scalars().all()
    return [PlaygroundMediaOut.model_validate(r) for r in rows]


@router.get("/media/{media_id}/file")
async def serve_media_file(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """본인 미디어 파일 서빙. file_path 가 있으면 디스크에서 직접 (영구 보관)."""
    row = (
        await db.execute(
            select(PlaygroundMedia).where(PlaygroundMedia.id == media_id)
        )
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    if not row.file_path or not os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="파일이 아직 준비되지 않았습니다")
    media_root = os.path.abspath(settings.playground_media_root)
    real_path = os.path.abspath(row.file_path)
    # path traversal 차단
    if not real_path.startswith(media_root + os.sep):
        raise HTTPException(status_code=403, detail="허용되지 않은 경로")
    return FileResponse(real_path)
