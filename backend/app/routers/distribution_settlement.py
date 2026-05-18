"""신사업유통 정산 (자금 흐름) 라우터 (T9 Phase F-C).

main.py 에서 별도 include:
    app.include_router(distribution_settlement.router)

엔드포인트:
| 메서드 | 경로                                          | 설명                       |
|--------|-----------------------------------------------|----------------------------|
| GET    | /api/distribution/settlement/cash-flow        | 주차별 정산 행 (회사 옵션) |
| GET    | /api/distribution/settlement/summary          | 정산 요약 KPI              |
| GET    | /api/distribution/settlement/by-company       | 회사별 합계 (4개 행)       |
| GET    | /api/distribution/settlement/companies        | 회사 목록 (Select 채움)    |

설계:
- 기간 필터는 query string ``from`` / ``to`` (alias). 둘 다 옵션. None 이면 전체.
- ``company_label`` 도 옵션 — None 이면 전체 회사 합산 (by-company 제외).
- 라우터 전체 ``require_admin`` 게이트.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.distribution_settlement import (
    ByCompanyItem,
    CashFlowItem,
    CompaniesList,
    SettlementSummary,
)
from app.services.distribution import settlement_service

try:
    from app.services.distribution.constants import DISTRIBUTION_COMPANIES
except ImportError:  # pragma: no cover - constants 미생성 fallback
    DISTRIBUTION_COMPANIES = ("TK101", "래더엑스", "뉴테인핏", "SYBT")

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/distribution/settlement",
    tags=["distribution-settlement"],
    dependencies=[Depends(require_admin)],
)


@router.get("/cash-flow", response_model=list[CashFlowItem])
async def get_cash_flow(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    company_label: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[CashFlowItem]:
    """주차별 정산 행. period_start 오름차순.

    한 행 = 1주차 × 1회사. ``company_label`` 미지정 시 전체 회사 행 모두 반환.
    """
    rows = await settlement_service.cash_flow(
        db,
        from_date=from_date,
        to_date=to_date,
        company_label=company_label,
    )
    return [CashFlowItem(**row) for row in rows]


@router.get("/summary", response_model=SettlementSummary)
async def get_summary(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    company_label: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SettlementSummary:
    """정산 요약 KPI. 필터 조건 안에서의 총합."""
    data = await settlement_service.summary(
        db,
        from_date=from_date,
        to_date=to_date,
        company_label=company_label,
    )
    return SettlementSummary(**data)


@router.get("/by-company", response_model=list[ByCompanyItem])
async def get_by_company(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> list[ByCompanyItem]:
    """회사별 합계 — 4개 회사 모두 포함 (0이어도)."""
    rows = await settlement_service.by_company(
        db,
        from_date=from_date,
        to_date=to_date,
    )
    return [ByCompanyItem(**row) for row in rows]


@router.get("/companies", response_model=CompaniesList)
async def list_companies() -> CompaniesList:
    """회사 목록 — frontend Select 옵션 채움."""
    return CompaniesList(items=list(DISTRIBUTION_COMPANIES))
