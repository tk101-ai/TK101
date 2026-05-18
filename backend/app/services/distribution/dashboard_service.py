"""신사업유통 대시보드 집계 서비스 (T9 Phase E-1).

라우터(`distribution_dashboard.py`)에서 호출되는 KPI/추이/분포 집계 함수 모음.

설계 원칙:
- 모든 함수는 `AsyncSession` + 옵션 기간(`from_date`, `to_date`)을 받는다.
- 기간 미지정 시 전체 데이터를 집계한다.
- Decimal 합계는 ``float`` 으로 직렬화 (Pydantic 응답 친화적).
  None safe — 빈 결과/NULL 합계는 0.0 으로 반환.
- 카테고리/브랜드 분포는 시점 데이터(``distribution_products``)라 기간 필터를 받지 않는다.
- 세션 상태 분포는 6개 status(`pending/approved/rejected/sending/sent/failed`)
  모두 항상 포함 (0이어도 누락 X).
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import (
    DistributionProduct,
    DistributionSendLog,
    DistributionSession,
    DistributionWeeklySummary,
)

logger = logging.getLogger(__name__)


# 세션 상태 6종 — 0건이어도 응답에 포함시키기 위한 고정 키 집합.
SESSION_STATUS_KEYS: tuple[str, ...] = (
    "pending",
    "approved",
    "rejected",
    "sending",
    "sent",
    "failed",
)


def _to_float(value: Decimal | float | int | None) -> float:
    """Decimal/None 안전 float 변환. NULL 합계는 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _to_int(value: int | None) -> int:
    """None 안전 int 변환."""
    if value is None:
        return 0
    return int(value)


def _apply_weekly_period_filter(stmt, from_date: date_cls | None, to_date: date_cls | None):
    """``distribution_weekly_summary`` period_start 기준 기간 필터.

    weekly 행은 1주 범위라 period_start 단일 기준만 사용 (양 끝 포함).
    """
    if from_date is not None:
        stmt = stmt.where(DistributionWeeklySummary.period_start >= from_date)
    if to_date is not None:
        stmt = stmt.where(DistributionWeeklySummary.period_start <= to_date)
    return stmt


def _apply_session_period_filter(stmt, from_date: date_cls | None, to_date: date_cls | None):
    """``distribution_sessions.generated_at`` 기준 기간 필터."""
    if from_date is not None:
        stmt = stmt.where(func.date(DistributionSession.generated_at) >= from_date)
    if to_date is not None:
        stmt = stmt.where(func.date(DistributionSession.generated_at) <= to_date)
    return stmt


def _apply_send_log_period_filter(stmt, from_date: date_cls | None, to_date: date_cls | None):
    """``distribution_send_log.attempted_at`` 기준 기간 필터."""
    if from_date is not None:
        stmt = stmt.where(func.date(DistributionSendLog.attempted_at) >= from_date)
    if to_date is not None:
        stmt = stmt.where(func.date(DistributionSendLog.attempted_at) <= to_date)
    return stmt


# ---------------------------------------------------------------------------
# Overview — 전체 KPI 한 번에 집계
# ---------------------------------------------------------------------------


async def overview(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> dict[str, Any]:
    """전체 KPI dict.

    포함 키:
    - 매입/매출/입금 합계 (weekly_summary 기간 필터)
        total_kr_purchase, total_vn_inventory_move, total_vn_sales,
        total_deposit_req, total_account_deposit, total_cash_deposit
    - 제품/재고 (products — 시점 데이터, 기간 무관)
        product_count, total_purchase_qty, total_stock_qty
    - 세션 (sessions 기간 필터)
        session_count, approved_count, sent_count, failed_count,
        total_llm_cost_usd
    """
    # 1) weekly_summary 합계 — 단일 쿼리로 묶음.
    weekly_stmt = select(
        func.coalesce(func.sum(DistributionWeeklySummary.kr_purchase), 0).label("kr_purchase"),
        func.coalesce(func.sum(DistributionWeeklySummary.vn_inventory_move), 0).label("vn_inventory_move"),
        func.coalesce(func.sum(DistributionWeeklySummary.vn_sales_completed), 0).label("vn_sales"),
        # 입금요청 3종 합계 (KR매입 + VN재고 + VN매출).
        func.coalesce(
            func.sum(
                func.coalesce(DistributionWeeklySummary.kr_purchase_deposit_req, 0)
                + func.coalesce(DistributionWeeklySummary.vn_inventory_deposit_req, 0)
                + func.coalesce(DistributionWeeklySummary.vn_sales_deposit_req, 0)
            ),
            0,
        ).label("deposit_req"),
        func.coalesce(func.sum(DistributionWeeklySummary.account_deposit), 0).label("account_deposit"),
        func.coalesce(func.sum(DistributionWeeklySummary.cash_deposit), 0).label("cash_deposit"),
    )
    weekly_stmt = _apply_weekly_period_filter(weekly_stmt, from_date, to_date)
    weekly_row = (await db.execute(weekly_stmt)).one()

    # 2) 제품/재고 — 기간 무관.
    products_stmt = select(
        func.count(DistributionProduct.id).label("product_count"),
        func.coalesce(func.sum(DistributionProduct.purchase_qty), 0).label("purchase_qty"),
        func.coalesce(func.sum(DistributionProduct.domestic_stock_qty), 0).label("stock_qty"),
    )
    products_row = (await db.execute(products_stmt)).one()

    # 3) 세션 — 기간 필터.
    sessions_stmt = select(
        func.count(DistributionSession.id).label("session_count"),
        func.coalesce(
            func.sum(case((DistributionSession.status == "approved", 1), else_=0)), 0
        ).label("approved_count"),
        func.coalesce(
            func.sum(case((DistributionSession.status == "sent", 1), else_=0)), 0
        ).label("sent_count"),
        func.coalesce(
            func.sum(case((DistributionSession.status == "failed", 1), else_=0)), 0
        ).label("failed_count"),
        func.coalesce(func.sum(DistributionSession.llm_cost_usd), 0).label("llm_cost"),
    )
    sessions_stmt = _apply_session_period_filter(sessions_stmt, from_date, to_date)
    sessions_row = (await db.execute(sessions_stmt)).one()

    return {
        "total_kr_purchase": _to_float(weekly_row.kr_purchase),
        "total_vn_inventory_move": _to_float(weekly_row.vn_inventory_move),
        "total_vn_sales": _to_float(weekly_row.vn_sales),
        "total_deposit_req": _to_float(weekly_row.deposit_req),
        "total_account_deposit": _to_float(weekly_row.account_deposit),
        "total_cash_deposit": _to_float(weekly_row.cash_deposit),
        "product_count": _to_int(products_row.product_count),
        "total_purchase_qty": _to_int(products_row.purchase_qty),
        "total_stock_qty": _to_int(products_row.stock_qty),
        "session_count": _to_int(sessions_row.session_count),
        "approved_count": _to_int(sessions_row.approved_count),
        "sent_count": _to_int(sessions_row.sent_count),
        "failed_count": _to_int(sessions_row.failed_count),
        "total_llm_cost_usd": _to_float(sessions_row.llm_cost),
    }


# ---------------------------------------------------------------------------
# Weekly Trends — 주차별 추이
# ---------------------------------------------------------------------------


async def weekly_trends(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> list[dict[str, Any]]:
    """주차별 추이 리스트 (period_start 오름차순).

    한 주에 여러 회사가 있을 수 있어 같은 period_start 끼리 SUM.
    period_label 은 첫 번째 회사의 라벨을 채택 (회사가 1개여도 표시 일관).
    """
    stmt = (
        select(
            DistributionWeeklySummary.period_start.label("period_start"),
            func.min(DistributionWeeklySummary.period_label).label("period_label"),
            func.coalesce(func.sum(DistributionWeeklySummary.kr_purchase), 0).label("kr_purchase"),
            func.coalesce(func.sum(DistributionWeeklySummary.vn_inventory_move), 0).label("vn_inventory_move"),
            func.coalesce(func.sum(DistributionWeeklySummary.vn_sales_completed), 0).label("vn_sales_completed"),
            func.coalesce(
                func.sum(
                    func.coalesce(DistributionWeeklySummary.account_deposit, 0)
                    + func.coalesce(DistributionWeeklySummary.cash_deposit, 0)
                ),
                0,
            ).label("deposit_total"),
        )
        .group_by(DistributionWeeklySummary.period_start)
        .order_by(DistributionWeeklySummary.period_start.asc())
    )
    stmt = _apply_weekly_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    return [
        {
            "period_start": row.period_start,
            "period_label": row.period_label or "",
            "kr_purchase": _to_float(row.kr_purchase),
            "vn_inventory_move": _to_float(row.vn_inventory_move),
            "vn_sales_completed": _to_float(row.vn_sales_completed),
            "deposit_total": _to_float(row.deposit_total),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Category Distribution — 카테고리별 제품/재고
# ---------------------------------------------------------------------------


async def category_distribution(db: AsyncSession) -> list[dict[str, Any]]:
    """카테고리별 제품/매입수량/재고 합계.

    `products` 테이블은 시점 데이터라 기간 필터를 받지 않는다.
    카테고리 NULL 행은 "미분류" 로 묶어 표시.
    """
    category_label = func.coalesce(DistributionProduct.category, "미분류").label("category")
    stmt = (
        select(
            category_label,
            func.count(DistributionProduct.id).label("product_count"),
            func.coalesce(func.sum(DistributionProduct.purchase_qty), 0).label("purchase_qty"),
            func.coalesce(func.sum(DistributionProduct.domestic_stock_qty), 0).label("stock_qty"),
        )
        .group_by(category_label)
        .order_by(func.count(DistributionProduct.id).desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        {
            "category": row.category,
            "product_count": _to_int(row.product_count),
            "total_purchase_qty": _to_int(row.purchase_qty),
            "total_stock_qty": _to_int(row.stock_qty),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Brand Distribution — 상위 N 브랜드
# ---------------------------------------------------------------------------


async def brand_distribution(
    db: AsyncSession,
    *,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """재고 기준 상위 N 브랜드.

    정렬 기준: total_stock_qty DESC → product_count DESC → brand ASC
    """
    stmt = (
        select(
            DistributionProduct.brand.label("brand"),
            func.count(DistributionProduct.id).label("product_count"),
            func.coalesce(func.sum(DistributionProduct.domestic_stock_qty), 0).label("stock_qty"),
        )
        .group_by(DistributionProduct.brand)
        .order_by(
            func.coalesce(func.sum(DistributionProduct.domestic_stock_qty), 0).desc(),
            func.count(DistributionProduct.id).desc(),
            DistributionProduct.brand.asc(),
        )
        .limit(top_n)
    )
    rows = (await db.execute(stmt)).all()

    return [
        {
            "brand": row.brand,
            "product_count": _to_int(row.product_count),
            "total_stock_qty": _to_int(row.stock_qty),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Session Status Breakdown — 6개 status 모두 포함
# ---------------------------------------------------------------------------


async def session_status_breakdown(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> list[dict[str, Any]]:
    """세션 상태별 건수.

    SESSION_STATUS_KEYS 6개를 항상 포함 — 0건도 누락 X.
    프론트가 라벨/색 매핑을 안정적으로 할 수 있도록 고정 순서 보장.
    """
    stmt = select(
        DistributionSession.status.label("status"),
        func.count(DistributionSession.id).label("count"),
    ).group_by(DistributionSession.status)
    stmt = _apply_session_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    counts = {row.status: _to_int(row.count) for row in rows}
    return [
        {"status": status, "count": counts.get(status, 0)}
        for status in SESSION_STATUS_KEYS
    ]


# ---------------------------------------------------------------------------
# Send Success Rate — 송신 성공률
# ---------------------------------------------------------------------------


async def send_success_rate(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> dict[str, Any]:
    """송신 성공률 통계.

    success 컬럼은 nullable (시도 중인 경우) — True/False 만 success/failed 로 카운트.
    success_rate 는 0.0~1.0 범위 (프론트가 % 변환).
    total_attempts 가 0이면 success_rate 도 0.0.
    """
    stmt = select(
        func.count(DistributionSendLog.id).label("total_attempts"),
        func.coalesce(
            func.sum(case((DistributionSendLog.success.is_(True), 1), else_=0)), 0
        ).label("success_count"),
        func.coalesce(
            func.sum(case((DistributionSendLog.success.is_(False), 1), else_=0)), 0
        ).label("failed_count"),
    )
    stmt = _apply_send_log_period_filter(stmt, from_date, to_date)
    row = (await db.execute(stmt)).one()

    total = _to_int(row.total_attempts)
    success = _to_int(row.success_count)
    failed = _to_int(row.failed_count)
    rate = (success / total) if total > 0 else 0.0

    return {
        "total_attempts": total,
        "success_count": success,
        "failed_count": failed,
        "success_rate": rate,
    }
