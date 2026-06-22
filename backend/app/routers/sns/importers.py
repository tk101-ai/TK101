"""SNS 엑셀 임포트 — marketing1 워크북 업로드."""

import io
import logging
import os

from fastapi import Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.sns import ImportResponse

from ._common import MAX_UPLOAD_BYTES, router

logger = logging.getLogger("app.routers.sns")

# ---------------- 엑셀 임포트 ----------------


@router.post("/import/marketing1-excel", response_model=ImportResponse)
async def import_marketing1_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기 초과 (최대 10MB)")

    safe_filename = os.path.basename(file.filename or "marketing1.xlsx")
    if not safe_filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=415, detail="엑셀 파일(.xlsx/.xls)만 업로드 가능합니다")

    try:
        from app.services.sns_importers.marketing1 import import_to_db, parse_workbook
    except ImportError as exc:
        logger.exception("marketing1 임포터 로딩 실패")
        raise HTTPException(
            status_code=500, detail=f"임포터 로딩 실패: {type(exc).__name__}"
        )

    try:
        parsed = parse_workbook(io.BytesIO(contents))
        result = await import_to_db(db, parsed)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"엑셀 파싱 실패: {exc}")
    except Exception as exc:
        await db.rollback()
        logger.exception("marketing1 엑셀 임포트 실패")
        raise HTTPException(
            status_code=500, detail=f"임포트 실패: {type(exc).__name__}"
        )

    return ImportResponse(
        accounts_added=result.get("accounts_added", 0),
        snapshots_added=result.get("snapshots_added", 0),
        posts_added=result.get("posts_added", 0),
        posts_updated=result.get("posts_updated", 0),
    )
