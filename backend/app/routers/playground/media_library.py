"""콘텐츠 라이브러리 — 본인 미디어 목록·삭제·공유 + 공유 갤러리 + 파일 서빙.

스코프:
- 내 보관함: 본인이 만든 모든 미디어(상태 무관) 최신순.
- 공유 갤러리: ``is_shared=true`` + 성공 + 파일 보유 미디어를 사용자 전체가 열람.
- 공유 토글/삭제는 소유자만. 파일 서빙은 소유자 또는 공유된 미디어면 허용.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.playground import PlaygroundMedia
from app.models.user import User
from app.schemas.playground import (
    MediaShareRequest,
    PlaygroundMediaOut,
    SharedMediaOut,
)

from ._common import make_subrouter

logger = logging.getLogger(__name__)

router: APIRouter = make_subrouter()


async def _fetch_media_or_404(
    db: AsyncSession, media_id: uuid.UUID
) -> PlaygroundMedia:
    row = (
        await db.execute(
            select(PlaygroundMedia).where(PlaygroundMedia.id == media_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    return row


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


@router.get("/media/shared", response_model=list[SharedMediaOut])
async def list_shared_media(
    kind: Literal["image", "video"] | None = Query(default=None),
    q: str | None = Query(default=None, description="프롬프트 부분검색"),
    limit: int = Query(default=60, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SharedMediaOut]:
    """공유 갤러리 — 사용자 전체가 공유한 미디어(성공 + 파일 보유) 최신 공유순.

    본인이 공유한 것도 함께 노출되며 ``is_mine`` 으로 구분한다.
    """
    stmt = (
        select(PlaygroundMedia, User.name, User.department)
        .join(User, User.id == PlaygroundMedia.user_id)
        .where(
            PlaygroundMedia.is_shared.is_(True),
            PlaygroundMedia.status == "succeeded",
            PlaygroundMedia.file_path.is_not(None),
        )
        .order_by(desc(PlaygroundMedia.shared_at))
        .limit(limit)
    )
    if kind:
        stmt = stmt.where(PlaygroundMedia.media_type == kind)
    if q:
        stmt = stmt.where(PlaygroundMedia.prompt.ilike(f"%{q}%"))

    rows = (await db.execute(stmt)).all()
    out: list[SharedMediaOut] = []
    for media, owner_name, owner_dept in rows:
        item = SharedMediaOut.model_validate(media)
        item.owner_name = owner_name
        item.owner_department = owner_dept
        item.is_mine = media.user_id == user.id
        out.append(item)
    return out


@router.get("/media/{media_id}", response_model=PlaygroundMediaOut)
async def get_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundMediaOut:
    """미디어 1건 메타(재생성 폼 프리필용). 소유자 또는 공유 미디어면 허용."""
    row = await _fetch_media_or_404(db, media_id)
    if row.user_id != user.id and not row.is_shared:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    return PlaygroundMediaOut.model_validate(row)


@router.patch("/media/{media_id}/share", response_model=PlaygroundMediaOut)
async def set_media_shared(
    media_id: uuid.UUID,
    body: MediaShareRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundMediaOut:
    """공유 on/off 토글 — 소유자만. 성공 + 파일 보유 미디어만 공유 가능."""
    row = await _fetch_media_or_404(db, media_id)
    if row.user_id != user.id:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    if body.is_shared and (row.status != "succeeded" or not row.file_path):
        raise HTTPException(
            status_code=400, detail="완료된 미디어만 공유할 수 있습니다"
        )
    row.is_shared = body.is_shared
    row.shared_at = func.now() if body.is_shared else None
    await db.commit()
    await db.refresh(row)
    return PlaygroundMediaOut.model_validate(row)


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """본인 미디어 삭제 — DB row + 디스크 파일. 공유 중이어도 소유자면 삭제 가능."""
    row = await _fetch_media_or_404(db, media_id)
    if row.user_id != user.id:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    if row.file_path:
        media_root = os.path.abspath(settings.playground_media_root)
        real_path = os.path.abspath(row.file_path)
        # path traversal 차단 — 허용 루트 밖이면 파일은 건드리지 않고 row 만 제거.
        if real_path.startswith(media_root + os.sep) and os.path.exists(real_path):
            try:
                os.remove(real_path)
            except OSError:
                logger.warning("미디어 파일 삭제 실패 — DB row 만 제거", exc_info=True)
    await db.delete(row)
    await db.commit()


@router.get("/media/{media_id}/file")
async def serve_media_file(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """미디어 파일 서빙. 소유자 또는 공유된 미디어면 허용 (영구 보관 디스크에서)."""
    row = await _fetch_media_or_404(db, media_id)
    if row.user_id != user.id and not row.is_shared:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    if not row.file_path or not os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="파일이 아직 준비되지 않았습니다")
    media_root = os.path.abspath(settings.playground_media_root)
    real_path = os.path.abspath(row.file_path)
    # path traversal 차단
    if not real_path.startswith(media_root + os.sep):
        raise HTTPException(status_code=403, detail="허용되지 않은 경로")
    return FileResponse(real_path)
