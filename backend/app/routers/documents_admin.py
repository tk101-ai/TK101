"""관리자 전용 문서 사용량(토큰/비용) 집계 라우터 (PR-E #1).

GET /api/documents/admin/usage — form_jobs 단일 테이블을 kind(fill/generate) 별로
집계해 관리자에게 일별/사용자별/종류별 토큰·비용을 노출한다. require_admin(403)으로 가드.

fill·generate 를 한 테이블에서 집계하는 것이 form_jobs 일반화의 핵심 이득.
(kind, created_at DESC) 인덱스가 집계 쿼리를 backing 한다.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.form_filler import FormJob
from app.models.user import User
from app.schemas.documents_admin import (
    GroupBy,
    KindFilter,
    UsageResponse,
    UsageRow,
    UsageTotals,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/documents/admin",
    tags=["documents-admin"],
    dependencies=[Depends(require_admin)],
)

_DEFAULT_WINDOW_DAYS = 30


def _resolve_window(start: date | None, end: date | None) -> tuple[date, date]:
    """기간 기본값 — 최근 30일. start/end 중 하나만 주면 나머지 보정."""
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=_DEFAULT_WINDOW_DAYS)
    return start, end


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    start: date | None = Query(default=None, description="집계 시작일(포함). 기본 최근 30일."),
    end: date | None = Query(default=None, description="집계 종료일(포함). 기본 오늘."),
    group_by: GroupBy = Query(default="day"),
    kind: KindFilter = Query(default="all"),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    """form_jobs 토큰/비용 집계 — group_by(day/user/kind) + kind 필터.

    - day: created_at 을 date_trunc('day') 로 버킷팅.
    - user: users 조인해 표시명(name) 으로 버킷팅.
    - kind: fill/generate 로 버킷팅.
    """
    start, end = _resolve_window(start, end)
    # end 는 포함이므로 [start 00:00, end+1 00:00) 반열림 구간으로 비교.
    end_exclusive = end + timedelta(days=1)

    filters = [
        FormJob.created_at >= start,
        FormJob.created_at < end_exclusive,
    ]
    if kind != "all":
        filters.append(FormJob.kind == kind)

    # cost_usd(Numeric) 합계 — 응답에서 float 로 직렬화(아래 float() 변환).
    cost_sum = func.coalesce(func.sum(FormJob.cost_usd), 0)
    count_col = func.count(FormJob.id)
    tin_sum = func.coalesce(func.sum(FormJob.total_tokens_in), 0)
    tout_sum = func.coalesce(func.sum(FormJob.total_tokens_out), 0)

    if group_by == "user":
        stmt = (
            select(
                func.coalesce(User.name, "(알 수 없음)").label("bucket"),
                count_col.label("job_count"),
                tin_sum.label("tokens_in"),
                tout_sum.label("tokens_out"),
                cost_sum.label("cost_usd"),
            )
            .select_from(FormJob)
            .join(User, User.id == FormJob.user_id, isouter=True)
            .where(*filters)
            .group_by(func.coalesce(User.name, "(알 수 없음)"))
            .order_by(cost_sum.desc())
        )
        rows = (await db.execute(stmt)).all()
        usage_rows = [
            UsageRow(
                bucket=str(r.bucket),
                kind=None,
                job_count=int(r.job_count),
                tokens_in=int(r.tokens_in),
                tokens_out=int(r.tokens_out),
                cost_usd=float(r.cost_usd),
            )
            for r in rows
        ]
    elif group_by == "kind":
        stmt = (
            select(
                FormJob.kind.label("bucket"),
                count_col.label("job_count"),
                tin_sum.label("tokens_in"),
                tout_sum.label("tokens_out"),
                cost_sum.label("cost_usd"),
            )
            .where(*filters)
            .group_by(FormJob.kind)
            .order_by(FormJob.kind)
        )
        rows = (await db.execute(stmt)).all()
        usage_rows = [
            UsageRow(
                bucket=str(r.bucket),
                kind=str(r.bucket),
                job_count=int(r.job_count),
                tokens_in=int(r.tokens_in),
                tokens_out=int(r.tokens_out),
                cost_usd=float(r.cost_usd),
            )
            for r in rows
        ]
    else:  # day
        day_bucket = func.date_trunc("day", FormJob.created_at)
        stmt = (
            select(
                day_bucket.label("bucket"),
                count_col.label("job_count"),
                tin_sum.label("tokens_in"),
                tout_sum.label("tokens_out"),
                cost_sum.label("cost_usd"),
            )
            .where(*filters)
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
        rows = (await db.execute(stmt)).all()
        usage_rows = [
            UsageRow(
                bucket=r.bucket.date().isoformat() if r.bucket else "",
                kind=None,
                job_count=int(r.job_count),
                tokens_in=int(r.tokens_in),
                tokens_out=int(r.tokens_out),
                cost_usd=float(r.cost_usd),
            )
            for r in rows
        ]

    totals = UsageTotals(
        job_count=sum(r.job_count for r in usage_rows),
        tokens_in=sum(r.tokens_in for r in usage_rows),
        tokens_out=sum(r.tokens_out for r in usage_rows),
        cost_usd=round(sum(r.cost_usd for r in usage_rows), 4),
    )
    return UsageResponse(
        group_by=group_by,
        start=start,
        end=end,
        rows=usage_rows,
        totals=totals,
    )
