import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.upload_log import UploadLog
from app.models.user import User
from app.schemas.upload_log import UploadLogRead
from app.services.excel import parse_bank_excel

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/transactions", response_model=UploadLogRead, status_code=status.HTTP_201_CREATED)
async def upload_transactions(
    account_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("admin", "accountant"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # Verify account exists
    result = await db.execute(select(Account).where(Account.id == account_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    contents = await file.read()
    file_bytes = io.BytesIO(contents)

    log = UploadLog(
        user_id=current_user.id,
        filename=file.filename or "unknown.xlsx",
        upload_type="transaction",
        account_id=account_id,
        status="processing",
    )
    db.add(log)
    await db.flush()

    try:
        parsed = parse_bank_excel(file_bytes)
        transactions = []
        for row in parsed:
            txn = Transaction(
                account_id=account_id,
                upload_log_id=log.id,
                **row,
            )
            transactions.append(txn)

        db.add_all(transactions)
        log.row_count = len(transactions)
        log.status = "completed"
    except Exception as e:
        log.status = "failed"
        log.error_detail = {"error": str(e)}

    await db.commit()
    await db.refresh(log)
    return log


@router.get("", response_model=list[UploadLogRead])
async def list_uploads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UploadLog).order_by(UploadLog.created_at.desc()))
    return result.scalars().all()
