"""신사업유통 대시보드 라우터 (T9 Phase E-1).

main.py 에서 별도 include:
    app.include_router(distribution_dashboard.router)

엔드포인트:
| 메서드 | 경로                                                          | 설명                  |
|--------|---------------------------------------------------------------|-----------------------|
| GET    | /api/distribution/dashboard/overview                          | KPI 카드 일괄 조회    |
| GET    | /api/distribution/dashboard/weekly-trends                     | 주차별 추이           |
| GET    | /api/distribution/dashboard/category-distribution             | 카테고리별 제품/재고  |
| GET    | /api/distribution/dashboard/brand-distribution                | 상위 N 브랜드         |
| GET    | /api/distribution/dashboard/session-status-breakdown          | 세션 상태별 건수      |
| GET    | /api/distribution/dashboard/send-success-rate                 | 송신 성공률           |

설계:
- 기간 필터는 query string ``from`` / ``to`` (alias). 둘 다 옵션. None 이면 전체.
- 카테고리/브랜드 분포는 시점 데이터라 기간 필터 X.
- 권한 (T9 라우터 가드 정책 통일): ``require_module(Module.DISTRIBUTION.value)`` — 신사업팀 사용 가능.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_module
from app.modules.constants import Module
from app.schemas.distribution_dashboard import (
    BrandDistItem,
    CategoryDistItem,
    OverviewOut,
    SendSuccessRateOut,
    StatusBreakdownItem,
    WeeklyTrendItem,
)
from app.services.distribution import dashboard_service

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/distribution/dashboard",
    tags=["distribution-dashboard"],
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
)


@router.get("/overview", response_model=OverviewOut)
async def get_overview(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> OverviewOut:
    """전체 KPI. 기간 미지정 시 전체 데이터."""
    data = await dashboard_service.overview(
        db, from_date=from_date, to_date=to_date
    )
    return OverviewOut(**data)


@router.get("/weekly-trends", response_model=list[WeeklyTrendItem])
async def get_weekly_trends(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> list[WeeklyTrendItem]:
    """주차별 추이 (period_start 오름차순)."""
    rows = await dashboard_service.weekly_trends(
        db, from_date=from_date, to_date=to_date
    )
    return [WeeklyTrendItem(**row) for row in rows]


@router.get("/category-distribution", response_model=list[CategoryDistItem])
async def get_category_distribution(
    db: AsyncSession = Depends(get_db),
) -> list[CategoryDistItem]:
    """카테고리별 제품/재고 분포 (시점 데이터, 기간 무관)."""
    rows = await dashboard_service.category_distribution(db)
    return [CategoryDistItem(**row) for row in rows]


@router.get("/brand-distribution", response_model=list[BrandDistItem])
async def get_brand_distribution(
    top_n: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[BrandDistItem]:
    """재고 기준 상위 N 브랜드 (시점 데이터, 기간 무관)."""
    rows = await dashboard_service.brand_distribution(db, top_n=top_n)
    return [BrandDistItem(**row) for row in rows]


@router.get("/session-status-breakdown", response_model=list[StatusBreakdownItem])
async def get_session_status_breakdown(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> list[StatusBreakdownItem]:
    """세션 상태별 건수 — 6개 status 모두 포함."""
    rows = await dashboard_service.session_status_breakdown(
        db, from_date=from_date, to_date=to_date
    )
    return [StatusBreakdownItem(**row) for row in rows]


@router.get("/send-success-rate", response_model=SendSuccessRateOut)
async def get_send_success_rate(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> SendSuccessRateOut:
    """송신 성공률. success_rate 는 0.0~1.0."""
    data = await dashboard_service.send_success_rate(
        db, from_date=from_date, to_date=to_date
    )
    return SendSuccessRateOut(**data)
