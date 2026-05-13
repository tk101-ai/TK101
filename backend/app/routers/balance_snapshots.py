"""계좌 잔액 스냅샷 라우터 (Wave 2 백엔드 D).

엔드포인트:
- GET  /api/balance-snapshots             기간 시계열 조회 (interval=daily|monthly)
- POST /api/balance-snapshots/recompute   재계산 (admin only)

용도: 대시보드 잔액 추이 차트 (월말/일별).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.modules.constants import Module
from app.services.balance_snapshots import (
    get_snapshots,
    recompute_snapshots,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/balance-snapshots",
    tags=["balance-snapshots"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


# ---------------------------------------------------------------------------
# 응답 스키마
# ---------------------------------------------------------------------------
class BalanceSnapshotItem(BaseModel):
    account_id: uuid.UUID
    snapshot_date: date
    balance: str  # Decimal → str 직렬화 (프론트가 BigDecimal 처리)
    currency: str

    model_config = {"from_attributes": True}


class RecomputeRequest(BaseModel):
    account_id: uuid.UUID | None = None
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")

    model_config = {"populate_by_name": True}


class RecomputeResponse(BaseModel):
    computed_count: int
    account_count: int


# ---------------------------------------------------------------------------
# 1. 조회
# ---------------------------------------------------------------------------
@router.get("", response_model=list[BalanceSnapshotItem])
async def list_balance_snapshots(
    account_id: uuid.UUID = Query(..., description="계좌 ID"),
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    interval: str = Query(
        "monthly", pattern=r"^(daily|monthly)$", description="daily | monthly"
    ),
    db: AsyncSession = Depends(get_db),
):
    """기간 + 간격으로 스냅샷 조회. interval=monthly 가 기본."""
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from 이 to 보다 늦습니다",
        )
    try:
        rows = await get_snapshots(
            db, account_id, date_from, date_to, interval=interval
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return [
        BalanceSnapshotItem(
            account_id=r.account_id,
            snapshot_date=r.snapshot_date,
            balance=str(r.balance),
            currency=r.currency,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 2. 재계산 — admin only (비용 큰 작업)
# ---------------------------------------------------------------------------
@router.post(
    "/recompute",
    response_model=RecomputeResponse,
    dependencies=[Depends(require_admin)],
)
async def recompute_balance_snapshots(
    body: RecomputeRequest,
    db: AsyncSession = Depends(get_db),
):
    """지정 기간(또는 전체)의 일별 스냅샷 upsert.

    Body 비어있으면 모든 계좌 × 모든 거래 일자에 대해 재계산.
    데이터가 클 수 있어 admin 권한으로 게이트.
    """
    if (
        body.from_date is not None
        and body.to_date is not None
        and body.from_date > body.to_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from 이 to 보다 늦습니다",
        )

    try:
        computed, accounts = await recompute_snapshots(
            db,
            account_id=body.account_id,
            from_date=body.from_date,
            to_date=body.to_date,
        )
    except Exception as exc:  # noqa: BLE001 — 라우터 경계에서 일반화
        logger.exception("잔액 스냅샷 재계산 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="재계산 중 오류가 발생했습니다",
        ) from exc

    return RecomputeResponse(computed_count=computed, account_count=accounts)
