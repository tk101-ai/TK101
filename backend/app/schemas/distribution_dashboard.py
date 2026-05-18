"""신사업유통 대시보드 Pydantic 응답 스키마 (T9 Phase E-1).

라우터: ``app/routers/distribution_dashboard.py``
서비스: ``app/services/distribution/dashboard_service.py``

직렬화 정책:
- 금액·합계는 ``float`` (서비스 단에서 Decimal → float 변환 완료).
- 카운트는 ``int``.
- success_rate 는 0.0~1.0.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class OverviewOut(BaseModel):
    """대시보드 KPI 카드 8개를 한 번에 채우는 응답."""

    # 매입/매출/입금 (weekly_summary 기간 합계)
    total_kr_purchase: float
    total_vn_inventory_move: float
    total_vn_sales: float
    total_deposit_req: float
    total_account_deposit: float
    total_cash_deposit: float
    # 제품/재고 (products — 시점 데이터)
    product_count: int
    total_purchase_qty: int
    total_stock_qty: int
    # 세션 (기간 합계)
    session_count: int
    approved_count: int
    sent_count: int
    failed_count: int
    total_llm_cost_usd: float


class WeeklyTrendItem(BaseModel):
    """주차별 추이 1행. period_start 오름차순으로 응답."""

    period_start: date
    period_label: str
    kr_purchase: float
    vn_inventory_move: float
    vn_sales_completed: float
    deposit_total: float


class CategoryDistItem(BaseModel):
    """카테고리별 제품/재고 분포 1행."""

    category: str
    product_count: int
    total_purchase_qty: int
    total_stock_qty: int


class BrandDistItem(BaseModel):
    """상위 N 브랜드 1행 (재고 기준 내림차순)."""

    brand: str
    product_count: int
    total_stock_qty: int


class StatusBreakdownItem(BaseModel):
    """세션 상태별 건수 1행.

    status: pending / approved / rejected / sending / sent / failed
    6개 모두 항상 포함 (0건도 누락 X).
    """

    status: str
    count: int


class SendSuccessRateOut(BaseModel):
    """송신 성공률 응답.

    success_rate 는 0.0~1.0 (프론트가 100 곱해 % 표시).
    """

    total_attempts: int
    success_count: int
    failed_count: int
    success_rate: float = Field(ge=0.0, le=1.0)
