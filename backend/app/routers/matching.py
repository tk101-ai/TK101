from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.transaction import Transaction
from app.models.user import User
from app.services.matching import auto_match_internal_transactions
from app.services.reconcile import reconcile_invoices

router = APIRouter(prefix="/api/matching", tags=["matching"])


@router.post("/run")
async def run_matching(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("admin", "accountant"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    count = await auto_match_internal_transactions(db)
    return {"matched_count": count}


@router.post("/reconcile")
async def run_reconciliation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("admin", "accountant"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    count = await reconcile_invoices(db)
    return {"reconciled_count": count}
