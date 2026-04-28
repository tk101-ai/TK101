from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.services.matching import auto_match_internal_transactions
from app.services.reconcile import reconcile_invoices

router = APIRouter(
    prefix="/api/matching",
    tags=["matching"],
    dependencies=[Depends(require_module("finance"))],
)


@router.post("/run", dependencies=[Depends(require_admin)])
async def run_matching(db: AsyncSession = Depends(get_db)):
    count = await auto_match_internal_transactions(db)
    return {"matched_count": count}


@router.post("/reconcile", dependencies=[Depends(require_admin)])
async def run_reconciliation(db: AsyncSession = Depends(get_db)):
    count = await reconcile_invoices(db)
    return {"reconciled_count": count}
