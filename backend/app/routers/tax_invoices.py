from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.tax_invoice import TaxInvoice
from app.models.user import User
from app.schemas.tax_invoice import TaxInvoiceRead

router = APIRouter(prefix="/api/tax-invoices", tags=["tax-invoices"])


@router.get("", response_model=list[TaxInvoiceRead])
async def list_invoices(
    invoice_type: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    match_status: str | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(TaxInvoice).order_by(TaxInvoice.issue_date.desc())
    if invoice_type:
        query = query.where(TaxInvoice.invoice_type == invoice_type)
    if date_from:
        query = query.where(TaxInvoice.issue_date >= date_from)
    if date_to:
        query = query.where(TaxInvoice.issue_date <= date_to)
    if match_status:
        query = query.where(TaxInvoice.match_status == match_status)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


@router.patch("/{invoice_id}/transaction")
async def link_invoice_to_transaction(
    invoice_id: str,
    transaction_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("admin", "accountant"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    result = await db.execute(select(TaxInvoice).where(TaxInvoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    invoice.matched_transaction_id = transaction_id
    invoice.match_status = "manual"
    await db.commit()
    return {"status": "linked"}
