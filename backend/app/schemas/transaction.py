import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


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


class MemoUpdate(BaseModel):
    memo: str
