"""신사업유통 분석 페이지 라우터 (T9 Phase E-4).

main.py 에서 별도 include:
    app.include_router(distribution_analytics.router)

엔드포인트:
| 메서드 | 경로                                                  | 설명                  |
|--------|-------------------------------------------------------|-----------------------|
| GET    | /api/distribution/analytics/cost-by-day               | 일별 Claude 비용      |
| GET    | /api/distribution/analytics/cost-by-persona           | 페르소나별 비용       |
| GET    | /api/distribution/analytics/send-failures             | 송신 실패 원인 분류   |
| GET    | /api/distribution/analytics/session-status-counts     | status별 세션 카운트  |
| GET    | /api/distribution/analytics/search-messages           | 메시지 텍스트 검색    |

설계:
- 기간 필터는 query string ``from`` / ``to`` (alias). 둘 다 옵션. None 이면 전체.
- 메시지 검색의 ``q`` 는 필수 (min 1, max 100).
- 라우터 전체 ``require_admin`` 게이트.
- prefix 는 대시보드(``/api/distribution/dashboard``) 와 분리한 별도 라우터.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.distribution_analytics import (
    CostByDayItem,
    CostByPersonaItem,
    MessageSearchItem,
    SendFailureItem,
)
from app.services.distribution import analytics_service

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/distribution/analytics",
    tags=["distribution-analytics"],
    dependencies=[Depends(require_admin)],
)


@router.get("/cost-by-day", response_model=list[CostByDayItem])
async def get_cost_by_day(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> list[CostByDayItem]:
    """일별 Claude 비용 (date 오름차순)."""
    rows = await analytics_service.cost_by_day(
        db, from_date=from_date, to_date=to_date
    )
    return [CostByDayItem(**row) for row in rows]


@router.get("/cost-by-persona", response_model=list[CostByPersonaItem])
async def get_cost_by_persona(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> list[CostByPersonaItem]:
    """페르소나(sender)별 Claude 비용 (total_cost_usd 내림차순)."""
    rows = await analytics_service.cost_by_persona(
        db, from_date=from_date, to_date=to_date
    )
    return [CostByPersonaItem(**row) for row in rows]


@router.get("/send-failures", response_model=list[SendFailureItem])
async def get_send_failures(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> list[SendFailureItem]:
    """송신 실패 원인 분류 (count 내림차순)."""
    rows = await analytics_service.send_failure_breakdown(
        db, from_date=from_date, to_date=to_date
    )
    return [SendFailureItem(**row) for row in rows]


@router.get("/session-status-counts", response_model=dict[str, int])
async def get_session_status_counts(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """세션 상태별 카운트 dict — 6종 status 모두 포함."""
    return await analytics_service.session_count_by_status(
        db, from_date=from_date, to_date=to_date
    )


@router.get("/search-messages", response_model=list[MessageSearchItem])
async def search_messages(
    q: str = Query(..., min_length=1, max_length=100),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[MessageSearchItem]:
    """메시지 텍스트 검색 (ILIKE, content/edited_content OR)."""
    rows = await analytics_service.search_messages(
        db,
        query=q,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
    return [MessageSearchItem(**row) for row in rows]
