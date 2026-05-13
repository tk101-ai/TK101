"""계좌 Pydantic 스키마 — 마이그레이션 007 확장 필드 포함."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    bank_name: str
    account_number: str
    account_holder: str
    business_registration_no: str | None = None
    # 007 확장: 생성 시점에 외화/대출 여부와 통화/별칭 지정 가능.
    account_type: str | None = None  # general | foreign | loan | guaranteed_loan
    currency: str = Field(default="KRW", min_length=3, max_length=3)
    alias: str | None = None
    account_label: str | None = None


class AccountRead(BaseModel):
    id: uuid.UUID
    bank_name: str
    account_number: str
    account_holder: str
    business_registration_no: str | None
    is_active: bool
    created_at: datetime
    # 007 확장.
    account_type: str | None
    currency: str
    current_balance: Decimal | None
    last_synced_at: datetime | None
    account_label: str | None
    alias: str | None

    model_config = {"from_attributes": True}


class AccountUpdate(BaseModel):
    bank_name: str | None = None
    account_number: str | None = None
    account_holder: str | None = None
    business_registration_no: str | None = None
    is_active: bool | None = None
    # 007 확장.
    account_type: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    alias: str | None = None
    account_label: str | None = None
