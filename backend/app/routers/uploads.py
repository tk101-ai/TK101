import io
import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.upload_log import UploadLog
from app.models.user import User
from app.modules.constants import UserRole
from app.schemas.upload_log import UploadLogRead
from app.services.excel import parse_bank_excel

router = APIRouter(
    prefix="/api/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_module("finance"))],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_TXN_FIELDS = {
    "transaction_date",
    "amount",
    "balance",
    "counterpart_name",
    "description",
    "transaction_type",
}


@router.post("/transactions", response_model=UploadLogRead, status_code=status.HTTP_201_CREATED)
async def upload_transactions(
    account_id: str = Query(...),
    bank_format: str | None = Query(
        None,
        description="은행 형식 (kb/ibk/nh/shinhan/woori/hana). 미지정시 계좌의 은행명으로 자동감지",
    ),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    detected_format = bank_format or account.bank_name

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기 초과 (최대 10MB)")
    file_bytes = io.BytesIO(contents)

    safe_filename = os.path.basename(file.filename or "unknown.xlsx")

    log = UploadLog(
        user_id=current_user.id,
        filename=safe_filename,
        upload_type="transaction",
        account_id=account_id,
        status="processing",
    )
    db.add(log)
    await db.flush()

    try:
        parsed = parse_bank_excel(file_bytes, bank_name=detected_format)
        transactions = []
        for row in parsed:
            safe_row = {k: v for k, v in row.items() if k in ALLOWED_TXN_FIELDS}
            txn = Transaction(account_id=account_id, upload_log_id=log.id, **safe_row)
            transactions.append(txn)

        db.add_all(transactions)
        log.row_count = len(transactions)
        log.status = "completed"
    except ValueError as e:
        log.status = "failed"
        log.error_detail = {"error": str(e), "type": "validation"}
        await db.commit()
        await db.refresh(log)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.status = "failed"
        log.error_detail = {"error": str(e)}
        await db.commit()
        await db.refresh(log)
        raise HTTPException(status_code=500, detail="파일 처리 중 오류가 발생했습니다")

    await db.commit()
    await db.refresh(log)
    return log


@router.get("", response_model=list[UploadLogRead])
async def list_uploads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(UploadLog).order_by(UploadLog.created_at.desc())
    if current_user.role != UserRole.ADMIN.value:
        query = query.where(UploadLog.user_id == current_user.id)
    result = await db.execute(query)
    return result.scalars().all()
