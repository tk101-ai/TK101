"""정산 (자금 흐름) 집계 서비스 (T9 Phase F-C).

엑셀 종합관리시트 기반 자금 흐름 집계:
- 매입 (kr_purchase + vn_inventory_move + vn_sales_completed)
- 입금요청 3종 (kr_purchase × 40% + vn_inventory_move × 30% + vn_sales_completed × 30%)
- 실 입금 (account_deposit + cash_deposit)
- 외상잔고 (시트 정의: kr_purchase - 실 입금)
- 이행률 (실 입금 / 입금요청 — 정산 진행도)

라우터: ``app/routers/distribution_settlement.py``

직렬화 정책:
- 모든 금액은 ``float`` (Decimal → float 변환). NULL 합계는 0.0.
- 이행률(``fulfillment_rate``)은 0.0~1.0 (req=0 일 때 0.0).
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import DistributionWeeklySummary

try:
    from app.services.distribution.constants import DISTRIBUTION_COMPANIES
except ImportError:  # pragma: no cover - constants 미생성 fallback
    DISTRIBUTION_COMPANIES = ("TK101", "래더엑스", "뉴테인핏", "SYBT")

logger = logging.getLogger(__name__)


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    """NULL → Decimal(0) 변환. 합계 계산에서 NoneType 합산 오류 방지."""
    if value is None:
        return Decimal(0)
    return value


def _to_float(value: Decimal | float | int | None) -> float:
    """Decimal/None 안전 float 변환. NULL 합계는 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _safe_ratio(numerator: Decimal | float, denominator: Decimal | float) -> float:
    """0 으로 나누기 방지. denominator 가 0 또는 None 이면 0.0 반환."""
    if denominator is None or float(denominator) == 0.0:
        return 0.0
    return float(numerator) / float(denominator)


async def cash_flow(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
    company_label: str | None,
) -> list[dict[str, Any]]:
    """주차별 정산 행 — period_start 오름차순.

    한 행 = 1주차 × 1회사. weekly_summary UNIQUE(company_label, period_start, period_end)
    제약에 따라 같은 회사·기간은 1행만 존재. 회사를 분리하지 않고 합산하지 않음
    (회사별 비교는 ``by_company`` 사용).

    필터:
    - from_date <= period_end (시작 이전에 끝나면 제외)
    - to_date >= period_start (종료 이후에 시작하면 제외)
      → 일부 겹치는 주차도 포함.
    - company_label 정확 일치 (None 이면 전체).
    """
    stmt = select(DistributionWeeklySummary)
    if from_date is not None:
        stmt = stmt.where(DistributionWeeklySummary.period_end >= from_date)
    if to_date is not None:
        stmt = stmt.where(DistributionWeeklySummary.period_start <= to_date)
    if company_label is not None:
        stmt = stmt.where(DistributionWeeklySummary.company_label == company_label)
    stmt = stmt.order_by(DistributionWeeklySummary.period_start.asc())
    rows = (await db.execute(stmt)).scalars().all()

    out: list[dict[str, Any]] = []
    for r in rows:
        kr_dep_req = _decimal_or_zero(r.kr_purchase_deposit_req)
        vn_inv_dep_req = _decimal_or_zero(r.vn_inventory_deposit_req)
        vn_sales_dep_req = _decimal_or_zero(r.vn_sales_deposit_req)
        deposit_req_total = kr_dep_req + vn_inv_dep_req + vn_sales_dep_req

        account_dep = _decimal_or_zero(r.account_deposit)
        cash_dep = _decimal_or_zero(r.cash_deposit)
        deposit_total = account_dep + cash_dep

        kr_purchase = _decimal_or_zero(r.kr_purchase)
        # 시트 정의: 외상잔고계 = kr_purchase - (account_deposit + cash_deposit)
        outstanding = kr_purchase - deposit_total

        fulfillment = _safe_ratio(deposit_total, deposit_req_total)

        out.append({
            "period_label": r.period_label,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "company_label": r.company_label,
            "kr_purchase": _to_float(r.kr_purchase),
            "vn_inventory_move": _to_float(r.vn_inventory_move),
            "vn_sales_completed": _to_float(r.vn_sales_completed),
            "kr_purchase_deposit_req": _to_float(r.kr_purchase_deposit_req),
            "vn_inventory_deposit_req": _to_float(r.vn_inventory_deposit_req),
            "vn_sales_deposit_req": _to_float(r.vn_sales_deposit_req),
            "deposit_req_total": float(deposit_req_total),
            "account_deposit": _to_float(r.account_deposit),
            "cash_deposit": _to_float(r.cash_deposit),
            "deposit_total": float(deposit_total),
            "outstanding_balance": float(outstanding),
            "fulfillment_rate": fulfillment,
        })
    return out


async def summary(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
    company_label: str | None,
) -> dict[str, Any]:
    """기간/회사 필터 적용 정산 요약 — 총합 수치.

    포함 키:
    - company_count: 등장한 회사 수 (필터 적용 후)
    - period_count: 주차 행 개수
    - total_kr_purchase, total_vn_inventory_move, total_vn_sales: 매입 3종 합계
    - total_deposit_req: 입금요청 총합 (3종 합)
    - total_deposit_received: 실 입금 총합 (account + cash)
    - total_outstanding: 외상잔고 합계 (kr_purchase 합 - 실 입금 합)
    - fulfillment_rate: 0.0~1.0 (req=0 일 때 0.0)
    - latest_period_label: 가장 최근 주차 라벨 (period_start DESC) — 없으면 None
    """
    rows = await cash_flow(
        db,
        from_date=from_date,
        to_date=to_date,
        company_label=company_label,
    )

    total_kr_purchase = 0.0
    total_vn_inventory_move = 0.0
    total_vn_sales = 0.0
    total_deposit_req = 0.0
    total_deposit_received = 0.0
    companies: set[str] = set()
    latest_label: str | None = None
    latest_start: date_cls | None = None

    for r in rows:
        total_kr_purchase += r["kr_purchase"]
        total_vn_inventory_move += r["vn_inventory_move"]
        total_vn_sales += r["vn_sales_completed"]
        total_deposit_req += r["deposit_req_total"]
        total_deposit_received += r["deposit_total"]
        companies.add(r["company_label"])
        period_start = r["period_start"]
        if latest_start is None or (period_start is not None and period_start > latest_start):
            latest_start = period_start
            latest_label = r["period_label"]

    total_outstanding = total_kr_purchase - total_deposit_received
    fulfillment_rate = _safe_ratio(total_deposit_received, total_deposit_req)

    return {
        "company_count": len(companies),
        "period_count": len(rows),
        "total_kr_purchase": total_kr_purchase,
        "total_vn_inventory_move": total_vn_inventory_move,
        "total_vn_sales": total_vn_sales,
        "total_deposit_req": total_deposit_req,
        "total_deposit_received": total_deposit_received,
        "total_outstanding": total_outstanding,
        "fulfillment_rate": fulfillment_rate,
        "latest_period_label": latest_label,
    }


async def by_company(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> list[dict[str, Any]]:
    """회사별 합계 — DISTRIBUTION_COMPANIES 4개 회사 모두 포함 (0이어도).

    UI 의 회사 비교 테이블에 사용. constants.DISTRIBUTION_COMPANIES 순서대로 반환.
    각 회사별로 ``cash_flow`` 를 호출해 합산 — 회사 수가 적어(4) 부담 없음.
    """
    out: list[dict[str, Any]] = []
    for company in DISTRIBUTION_COMPANIES:
        rows = await cash_flow(
            db,
            from_date=from_date,
            to_date=to_date,
            company_label=company,
        )
        total_kr_purchase = 0.0
        total_deposit_req = 0.0
        total_deposit_received = 0.0
        for r in rows:
            total_kr_purchase += r["kr_purchase"]
            total_deposit_req += r["deposit_req_total"]
            total_deposit_received += r["deposit_total"]
        total_outstanding = total_kr_purchase - total_deposit_received
        fulfillment_rate = _safe_ratio(total_deposit_received, total_deposit_req)

        out.append({
            "company_label": company,
            "period_count": len(rows),
            "total_kr_purchase": total_kr_purchase,
            "total_deposit_req": total_deposit_req,
            "total_deposit_received": total_deposit_received,
            "total_outstanding": total_outstanding,
            "fulfillment_rate": fulfillment_rate,
        })
    return out
