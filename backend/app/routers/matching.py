from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.modules.constants import Module
from app.services.matching import auto_match_internal_transactions
from app.services.reconcile import reconcile_invoices

router = APIRouter(
    prefix="/api/matching",
    tags=["matching"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


@router.post("/run", dependencies=[Depends(require_admin)])
async def run_matching(db: AsyncSession = Depends(get_db)):
    count = await auto_match_internal_transactions(db)
    # HIGH-8: 서비스가 flush 만 하므로 라우터에서 명시 커밋.
    await db.commit()
    return {"matched_count": count}


@router.post("/reconcile", dependencies=[Depends(require_admin)])
async def run_reconciliation(db: AsyncSession = Depends(get_db)):
    count = await reconcile_invoices(db)
    return {"reconciled_count": count}
