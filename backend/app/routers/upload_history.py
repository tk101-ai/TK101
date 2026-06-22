"""업로드 이력 라우터 (Wave 2 백엔드 D).

UploadLog 테이블 + Wave 1 신규 컬럼(duplicate_count / imported_count / bank_key / period_label)
을 페이지네이션/필터링으로 노출.

엔드포인트:
- GET /api/upload-history                  목록 (필터 + 페이지네이션)
- GET /api/upload-history/{id}             상세 (error_detail 포함)
- GET /api/upload-history/{id}/errors      에러 행 + xlsx 다운로드 가능 여부

업로더 본인/관리자 누구나 조회 가능 (require_module 만 적용; user 격리는 부서별 자료라 불필요).
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_module
from app.models.upload_log import UploadLog
from app.modules.constants import Module

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/upload-history",
    tags=["upload-history"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


# ---------------------------------------------------------------------------
# 응답 스키마
# ---------------------------------------------------------------------------
class UploadHistoryItem(BaseModel):
    """업로드 1건의 메타 응답 (Wave 1 컬럼 포함)."""

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    upload_type: str
    account_id: uuid.UUID | None
    bank_key: str | None
    period_label: str | None
    row_count: int
    imported_count: int
    duplicate_count: int
    error_count: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadHistoryDetail(UploadHistoryItem):
    """상세 응답 — error_detail JSON 포함."""

    error_detail: Any | None


class UploadHistoryPage(BaseModel):
    items: list[UploadHistoryItem]
    total: int
    page: int
    page_size: int


class UploadErrorRow(BaseModel):
    """error_detail 안의 한 줄."""

    row_number: int | None = None
    field: str | None = None
    message: str
    raw: Any | None = None


class UploadErrorsResponse(BaseModel):
    upload_id: uuid.UUID
    errors: list[UploadErrorRow]
    total: int
    download_url: str | None


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
async def _get_log(db: AsyncSession, upload_id: uuid.UUID) -> UploadLog:
    result = await db.execute(select(UploadLog).where(UploadLog.id == upload_id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="업로드 이력을 찾을 수 없습니다",
        )
    return log


def _coerce_error_rows(error_detail: Any) -> list[UploadErrorRow]:
    """error_detail JSON 을 균일한 UploadErrorRow 리스트로 정규화."""
    if not error_detail:
        return []
    rows: list[UploadErrorRow] = []
    # 케이스 1: {"error": "...", "type": "..."}  (단일 메시지)
    if isinstance(error_detail, dict):
        # errors 키가 리스트면 그걸 펼친다
        errs = error_detail.get("errors")
        if isinstance(errs, list):
            for e in errs:
                rows.append(_to_error_row(e))
            return rows
        # 그 외 → 단일 메시지로
        message = (
            error_detail.get("error")
            or error_detail.get("message")
            or str(error_detail)
        )
        rows.append(UploadErrorRow(message=str(message), raw=error_detail))
        return rows
    # 케이스 2: list
    if isinstance(error_detail, list):
        for e in error_detail:
            rows.append(_to_error_row(e))
        return rows
    return [UploadErrorRow(message=str(error_detail))]


def _to_error_row(entry: Any) -> UploadErrorRow:
    if isinstance(entry, dict):
        return UploadErrorRow(
            row_number=entry.get("row") or entry.get("row_number"),
            field=entry.get("field"),
            message=str(
                entry.get("message") or entry.get("error") or entry
            ),
            raw=entry,
        )
    return UploadErrorRow(message=str(entry))


# ---------------------------------------------------------------------------
# 1. 목록
# ---------------------------------------------------------------------------
@router.get("", response_model=UploadHistoryPage)
async def list_upload_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    account_id: uuid.UUID | None = Query(None),
    upload_status: str | None = Query(
        None, alias="status", description="processing | completed | failed"
    ),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
):
    """페이지네이션 + 필터링.

    필터:
      - account_id
      - status (alias=status)
      - from/to (UploadLog.created_at 기준 YYYY-MM-DD)
    """
    base_query = select(UploadLog)
    count_query = select(func.count()).select_from(UploadLog)

    conditions = []
    if account_id is not None:
        conditions.append(UploadLog.account_id == account_id)
    if upload_status is not None:
        conditions.append(UploadLog.status == upload_status)
    if date_from is not None:
        conditions.append(func.date(UploadLog.created_at) >= date_from)
    if date_to is not None:
        conditions.append(func.date(UploadLog.created_at) <= date_to)
    for cond in conditions:
        base_query = base_query.where(cond)
        count_query = count_query.where(cond)

    base_query = base_query.order_by(UploadLog.created_at.desc())
    base_query = base_query.limit(page_size).offset((page - 1) * page_size)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    result = await db.execute(base_query)
    items = result.scalars().all()

    return UploadHistoryPage(
        items=[UploadHistoryItem.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# 2. 상세
# ---------------------------------------------------------------------------
@router.get("/{upload_id}", response_model=UploadHistoryDetail)
async def get_upload_detail(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    log = await _get_log(db, upload_id)
    return UploadHistoryDetail.model_validate(log)


# ---------------------------------------------------------------------------
# 3. 에러 행 목록 / 다운로드
# ---------------------------------------------------------------------------
@router.get("/{upload_id}/errors", response_model=UploadErrorsResponse)
async def get_upload_errors(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """업로드 에러 메타 + xlsx 다운로드 URL."""
    log = await _get_log(db, upload_id)
    rows = _coerce_error_rows(log.error_detail)
    download_url: str | None = (
        f"/api/upload-history/{upload_id}/errors/download" if rows else None
    )
    return UploadErrorsResponse(
        upload_id=log.id,
        errors=rows,
        total=len(rows),
        download_url=download_url,
    )


@router.get("/{upload_id}/errors/download")
async def download_upload_errors(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """에러 행을 xlsx 로 묶어 다운로드.

    H5: upload_id 는 ``uuid.UUID`` 타입(형식 오류는 422). 파일명은 RFC5987 로
    인코딩해 Content-Disposition 헤더 인젝션(CR/LF·따옴표) 을 차단한다.
    """
    log = await _get_log(db, upload_id)
    rows = _coerce_error_rows(log.error_detail)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="에러 행이 없습니다"
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "업로드 오류"
    ws.append(["행번호", "필드", "메시지", "원본"])
    for r in rows:
        ws.append([r.row_number, r.field, r.message, str(r.raw or "")])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    # upload_id 는 UUID 라 안전하지만, 파일명은 RFC5987 로 항상 인코딩해
    # 헤더 인젝션 가능성을 원천 차단한다 (방어적).
    filename = f"upload_{upload_id}_errors.xlsx"
    quoted = quote(filename, safe="")
    content_disposition = (
        f"attachment; filename=\"{filename}\"; "
        f"filename*=UTF-8''{quoted}"
    )
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": content_disposition},
    )
