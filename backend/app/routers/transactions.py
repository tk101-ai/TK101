import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_module
from app.models.transaction import Transaction
from app.schemas.transaction import MemoUpdate, TransactionRead

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
    dependencies=[Depends(require_module("finance"))],
)


def _build_query(
    account_id: str | None,
    date_from: date | None,
    date_to: date | None,
    transaction_type: str | None,
    match_status: str | None,
    keyword: str | None,
):
    query = select(Transaction).order_by(Transaction.transaction_date.desc())
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.where(Transaction.transaction_date <= date_to)
    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
    if match_status:
        query = query.where(Transaction.match_status == match_status)
    if keyword:
        query = query.where(
            Transaction.counterpart_name.ilike(f"%{keyword}%")
            | Transaction.description.ilike(f"%{keyword}%")
            | Transaction.memo.ilike(f"%{keyword}%")
        )
    return query


@router.get("", response_model=list[TransactionRead])
async def list_transactions(
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    transaction_type: str | None = Query(None),
    match_status: str | None = Query(None),
    keyword: str | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    query = _build_query(account_id, date_from, date_to, transaction_type, match_status, keyword)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


@router.patch("/{transaction_id}/memo", response_model=TransactionRead)
async def update_memo(transaction_id: str, body: MemoUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    txn.memo = body.memo
    await db.commit()
    await db.refresh(txn)
    return txn


DOWNLOAD_MAX_ROWS = 50_000


@router.get("/download")
async def download_excel(
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    transaction_type: str | None = Query(None),
    match_status: str | None = Query(None),
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = _build_query(account_id, date_from, date_to, transaction_type, match_status, keyword)
    result = await db.execute(query.limit(DOWNLOAD_MAX_ROWS))
    rows = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "거래내역"
    ws.append(["거래일", "구분", "금액", "잔액", "상대방", "적요", "매칭상태", "메모"])
    for r in rows:
        ws.append([
            r.transaction_date.isoformat(),
            r.transaction_type,
            float(r.amount),
            float(r.balance) if r.balance else None,
            r.counterpart_name,
            r.description,
            r.match_status,
            r.memo,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"},
    )
