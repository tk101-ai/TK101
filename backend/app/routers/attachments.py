"""거래 영수증 첨부 라우터 (Wave 2 백엔드 D).

엔드포인트:
- POST   /api/transactions/{txn_id}/attachments              파일 업로드
- GET    /api/transactions/{txn_id}/attachments              메타 목록
- GET    /api/transactions/{txn_id}/attachments/{filename}   다운로드
- DELETE /api/transactions/{txn_id}/attachments/{filename}   삭제

저장 정책 / Path traversal 방지 등은 services.attachments 참조.
모든 엔드포인트는 finance 모듈 권한 필요.
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.transaction import Transaction
from app.models.user import User
from app.modules.constants import Module
from app.services.attachments import (
    MAX_SIZE,
    AttachmentError,
    delete_attachment,
    get_attachment_path,
    list_attachments,
    save_attachment,
)
from app.services.translation.translator import (
    RateLimitExceeded,
    check_rate_limit,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/transactions",
    tags=["transaction-attachments"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


# ---------------------------------------------------------------------------
# 응답 스키마
# ---------------------------------------------------------------------------
class AttachmentMeta(BaseModel):
    filename: str
    size: int
    content_type: str | None
    uploaded_at: datetime
    url: str


class AttachmentUploadResponse(BaseModel):
    transaction_id: uuid.UUID
    attachment_url: str
    file_size: int
    content_type: str | None
    filename: str


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
async def _get_transaction(
    db: AsyncSession, transaction_id: str
) -> Transaction:
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="거래를 찾을 수 없습니다"
        )
    if txn.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="삭제된 거래입니다"
        )
    return txn


def _attachment_error_to_http(exc: AttachmentError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


# ---------------------------------------------------------------------------
# 1. 업로드
# ---------------------------------------------------------------------------
@router.post(
    "/{transaction_id}/attachments",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    transaction_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """multipart/form-data 로 영수증/증빙 1건 업로드. Transaction.attachment_url 갱신."""
    # HIGH-10: 사용자별 분당 30회 레이트리밋 (스크립트/연속클릭 차단).
    try:
        check_rate_limit(str(user.id), max_calls=30, window_sec=60)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        ) from exc

    txn = await _get_transaction(db, transaction_id)

    # 컨테이너 내부 파일 시스템 사용. 운영 영구화는 docker-compose volume 추가가 권장사항.
    file_bytes = await file.read(MAX_SIZE + 1)
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"첨부 파일 크기가 한도({MAX_SIZE // (1024 * 1024)} MB)를 초과합니다",
        )
    try:
        info = save_attachment(
            account_id=str(txn.account_id),
            transaction_id=str(txn.id),
            file_bytes=file_bytes,
            original_filename=file.filename or "attachment",
            content_type=file.content_type,
        )
    except AttachmentError as exc:
        raise _attachment_error_to_http(exc) from exc

    txn.attachment_url = info.relative_url
    await db.commit()
    await db.refresh(txn)

    return AttachmentUploadResponse(
        transaction_id=txn.id,
        attachment_url=info.relative_url,
        file_size=info.size,
        content_type=info.content_type,
        filename=info.filename,
    )


# ---------------------------------------------------------------------------
# 2. 메타 목록
# ---------------------------------------------------------------------------
@router.get(
    "/{transaction_id}/attachments",
    response_model=list[AttachmentMeta],
)
async def list_transaction_attachments(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    """단건 모델이지만 list 반환 (다건 모델 호환 대비)."""
    txn = await _get_transaction(db, transaction_id)
    try:
        items = list_attachments(str(txn.account_id), str(txn.id))
    except AttachmentError as exc:
        raise _attachment_error_to_http(exc) from exc

    return [
        AttachmentMeta(
            filename=item.filename,
            size=item.size,
            content_type=item.content_type
            or mimetypes.guess_type(item.filename)[0],
            uploaded_at=item.uploaded_at,
            url=item.relative_url,
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# 3. 다운로드
# ---------------------------------------------------------------------------
@router.get("/{transaction_id}/attachments/{filename}")
async def download_attachment(
    transaction_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """안전 경로 검증 후 FileResponse 반환. ASCII-only 파일명 헤더 사용."""
    txn = await _get_transaction(db, transaction_id)
    try:
        path = get_attachment_path(
            str(txn.account_id), str(txn.id), filename
        )
    except AttachmentError as exc:
        raise _attachment_error_to_http(exc) from exc

    media_type = (
        mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )
    return FileResponse(path, media_type=media_type, filename=filename)


# ---------------------------------------------------------------------------
# 4. 삭제
# ---------------------------------------------------------------------------
@router.delete(
    "/{transaction_id}/attachments/{filename}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_attachment(
    transaction_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """파일 삭제 + Transaction.attachment_url = NULL (해당 파일이 활성 URL 일 때)."""
    txn = await _get_transaction(db, transaction_id)
    try:
        delete_attachment(str(txn.account_id), str(txn.id), filename)
    except AttachmentError as exc:
        raise _attachment_error_to_http(exc) from exc

    # attachment_url 이 이 파일을 가리키고 있으면 클리어
    if txn.attachment_url and txn.attachment_url.endswith(f"/{filename}"):
        txn.attachment_url = None
        await db.commit()
    return None
