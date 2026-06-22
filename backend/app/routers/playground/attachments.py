"""첨부 파일 — 업로드/서빙/삭제 + vision 모델 목록 (2026-05-20 추가)."""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.playground import PlaygroundAttachment
from app.models.user import User
from app.schemas.playground import PlaygroundAttachmentOut
from app.services.playground.attachments import (
    MAX_ATTACHMENT_BYTES,
    build_storage_path,
    detect_kind,
    extract_text,
)

from ._common import fetch_session_or_404, make_subrouter

logger = logging.getLogger(__name__)

router: APIRouter = make_subrouter()


@router.post(
    "/attachments",
    response_model=PlaygroundAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment_endpoint(
    file: UploadFile = File(...),
    session_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundAttachmentOut:
    """파일 1개 업로드. 이미지/PDF/텍스트/DOCX 지원.

    - session_id 가 주어지면 본인 세션이어야 함 (이후 그 세션 채팅에서만 사용).
    - session_id 미지정이면 처음 /chat 호출 시 자동으로 그 세션에 귀속.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="파일명이 비어있습니다")

    kind = detect_kind(file.filename, file.content_type)
    if kind is None:
        raise HTTPException(
            status_code=415,
            detail=f"지원하지 않는 파일 형식: {file.filename}",
        )

    # 크기 제한 — UploadFile 은 streaming 이라 read 후 길이 체크.
    raw = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다 (최대 {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB)",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일")

    # 세션 소유 검증.
    if session_id is not None:
        await fetch_session_or_404(db, session_id, user)

    file_id = uuid.uuid4()
    storage_path = build_storage_path(
        user_id=user.id,
        department=user.department,
        file_id=file_id,
        filename=file.filename,
    )
    try:
        storage_path.write_bytes(raw)
    except OSError as exc:
        logger.exception("첨부 저장 실패")
        raise HTTPException(
            status_code=500, detail=f"파일 저장 실패: {exc}"
        ) from exc

    extracted = extract_text(raw, kind) if kind != "image" else None

    row = PlaygroundAttachment(
        id=file_id,
        user_id=user.id,
        session_id=session_id,
        kind=kind,
        filename=file.filename,
        mime=file.content_type or "application/octet-stream",
        size_bytes=len(raw),
        file_path=str(storage_path),
        extracted_text=extracted or None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return PlaygroundAttachmentOut(
        id=row.id,
        user_id=row.user_id,
        session_id=row.session_id,
        kind=row.kind,
        filename=row.filename,
        mime=row.mime,
        size_bytes=row.size_bytes,
        has_extracted_text=bool(row.extracted_text),
        created_at=row.created_at,
    )


@router.get("/attachments/{attachment_id}/file")
async def serve_attachment_file(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """본인 첨부 파일 다운로드 (썸네일/미리보기 용)."""
    row = (
        await db.execute(
            select(PlaygroundAttachment).where(PlaygroundAttachment.id == attachment_id)
        )
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다")
    if not os.path.exists(row.file_path):
        raise HTTPException(status_code=410, detail="파일이 삭제되었습니다")
    media_root = os.path.abspath(settings.playground_media_root)
    real_path = os.path.abspath(row.file_path)
    if not real_path.startswith(media_root + os.sep):
        raise HTTPException(status_code=403, detail="허용되지 않은 경로")
    return FileResponse(real_path, media_type=row.mime, filename=row.filename)


@router.delete(
    "/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_attachment_endpoint(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """본인 첨부 파일 삭제 — DB row + 디스크 파일."""
    row = (
        await db.execute(
            select(PlaygroundAttachment).where(PlaygroundAttachment.id == attachment_id)
        )
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다")
    try:
        if os.path.exists(row.file_path):
            os.remove(row.file_path)
    except OSError:
        logger.warning("첨부 파일 삭제 실패 — DB row 만 제거", exc_info=True)
    await db.delete(row)
    await db.commit()


@router.get("/vision-models", response_model=list[str])
async def list_vision_models_endpoint(
    user: User = Depends(get_current_user),
) -> list[str]:
    """이미지 첨부 가능한 모델 ID 목록. 프론트는 이걸로 vision 미지원 모델 경고 노출."""
    from app.services.playground.attachments import VISION_MODELS

    return sorted(VISION_MODELS)
