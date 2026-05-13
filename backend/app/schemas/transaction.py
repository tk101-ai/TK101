"""거래 Pydantic 스키마 — 마이그레이션 007 확장 필드 포함.

설계 메모:
- TransactionFilter: 기존 min_amount/max_amount 유지. category_id/counterpart_id 신규 추가.
- TransactionRead: soft delete 필드 노출 (is_deleted). 조회 시 활성만 보려면 라우터에서 필터.
- TransactionCreate/Update: Wave 2 신규. 회계 기록 보존을 위해 Update 는 메타 필드만 허용.
- 집계 스키마: MonthlySummaryItem / TopCounterpartItem / CounterpartSuggestion / AccountBalanceItem
  대시보드/리포트 카드용 응답.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TransactionRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    transaction_date: date
    amount: Decimal
    balance: Decimal | None
    counterpart_name: str | None
    description: str | None
    transaction_type: str
    matched_transaction_id: uuid.UUID | None
    match_status: str
    memo: str | None
    created_at: datetime
    # 007 확장.
    transaction_hash: str | None
    category_id: uuid.UUID | None
    counterpart_id: uuid.UUID | None
    tags: list[str] | None
    attachment_url: str | None
    is_deleted: bool

    model_config = {"from_attributes": True}


class TransactionFilter(BaseModel):
    account_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    transaction_type: str | None = None
    match_status: str | None = None
    keyword: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    # 007 확장: 분류/거래처 필터.
    category_id: uuid.UUID | None = None
    counterpart_id: uuid.UUID | None = None
    # soft delete 토글. 기본은 미지정 → 라우터에서 활성만 노출 권장.
    include_deleted: bool = False


class MemoUpdate(BaseModel):
    memo: str


# ---------------------------------------------------------------------------
# Wave 2: 수동 등록 / 인라인 편집 / 매칭 워크북
# ---------------------------------------------------------------------------


class TransactionCreate(BaseModel):
    """수동 거래 등록 페이로드.

    transaction_hash 는 라우터에서 자동 계산 (account_id + date + amount + type + balance + description).
    """

    account_id: uuid.UUID
    transaction_date: date
    amount: Decimal = Field(..., gt=0)
    transaction_type: str = Field(..., pattern=r"^(deposit|withdrawal)$")
    balance: Decimal | None = None
    counterpart_name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category_id: uuid.UUID | None = None
    counterpart_id: uuid.UUID | None = None
    memo: str | None = None
    tags: list[str] | None = None


class TransactionUpdate(BaseModel):
    """인라인 편집 페이로드.

    회계 기록 보존을 위해 amount/transaction_date/transaction_type 은 변경 불가.
    """

    category_id: uuid.UUID | None = None
    counterpart_id: uuid.UUID | None = None
    counterpart_name: str | None = Field(default=None, max_length=200)
    memo: str | None = None
    tags: list[str] | None = None
    description: str | None = None


class TransactionMatchRequest(BaseModel):
    matched_transaction_id: uuid.UUID


# ---------------------------------------------------------------------------
# 집계 API 응답 스키마
# ---------------------------------------------------------------------------


class MonthlySummaryItem(BaseModel):
    month: str  # "YYYY-MM"
    deposit_total: Decimal
    withdrawal_total: Decimal
    net: Decimal
    count: int


class TopCounterpartItem(BaseModel):
    counterpart_name: str | None
    counterpart_id: uuid.UUID | None
    total_amount: Decimal
    count: int


class CounterpartSuggestion(BaseModel):
    name: str
    count: int
    counterpart_id: uuid.UUID | None = None


class AccountBalanceItem(BaseModel):
    account_id: uuid.UUID
    bank_name: str
    account_number: str
    account_type: str | None
    currency: str
    current_balance: Decimal | None
    last_synced_at: datetime | None
    last_transaction_date: date | None
