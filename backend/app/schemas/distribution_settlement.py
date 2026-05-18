"""신사업유통 정산 (자금 흐름) Pydantic 응답 스키마 (T9 Phase F-C).

라우터: ``app/routers/distribution_settlement.py``
서비스: ``app/services/distribution/settlement_service.py``

직렬화 정책:
- 모든 금액은 ``float`` (서비스 단에서 Decimal → float 변환 완료).
- 카운트는 ``int``.
- ``fulfillment_rate`` 는 0.0~1.0.
- 날짜는 ``date`` (FastAPI 가 ISO YYYY-MM-DD 직렬화).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CashFlowItem(BaseModel):
    """주차별 정산 1행 — period_start 오름차순으로 응답.

    1주차 × 1회사 = 1행. 매입 3종 + 입금요청 3종 + 실 입금 2종 + 외상잔고 + 이행률.
    """

    period_label: str
    period_start: date
    period_end: date
    company_label: str
    kr_purchase: float
    vn_inventory_move: float
    vn_sales_completed: float
    kr_purchase_deposit_req: float
    vn_inventory_deposit_req: float
    vn_sales_deposit_req: float
    deposit_req_total: float
    account_deposit: float
    cash_deposit: float
    deposit_total: float
    outstanding_balance: float
    fulfillment_rate: float = Field(ge=0.0)


class SettlementSummary(BaseModel):
    """정산 요약 (KPI 카드용)."""

    company_count: int
    period_count: int
    total_kr_purchase: float
    total_vn_inventory_move: float
    total_vn_sales: float
    total_deposit_req: float
    total_deposit_received: float
    total_outstanding: float
    fulfillment_rate: float = Field(ge=0.0)
    latest_period_label: str | None = None


class ByCompanyItem(BaseModel):
    """회사별 합계 1행 (회사 비교 테이블).

    DISTRIBUTION_COMPANIES 4개 회사 모두 포함 — 데이터 없는 회사도 0 값으로 표시.
    """

    company_label: str
    period_count: int
    total_kr_purchase: float
    total_deposit_req: float
    total_deposit_received: float
    total_outstanding: float
    fulfillment_rate: float = Field(ge=0.0)


class CompaniesList(BaseModel):
    """회사 목록 응답 (Select 옵션 채움용)."""

    items: list[str]
