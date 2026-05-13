"""은행 거래내역 자동 인식 + 계좌 자동 등록 라우터용 Pydantic 스키마."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.account import AccountCreate


class AccountMetaOut(BaseModel):
    bank_key: str
    bank_name: str
    account_number: str
    account_holder: str | None
    currency: str
    account_label: str | None
    period_year: int | None
    period_quarter: int | None


class SimilarAccountOut(BaseModel):
    id: str
    bank_name: str
    account_number: str
    account_holder: str | None
    currency: str
    account_label: str | None
    score: float


class ImportPreviewOut(BaseModel):
    file_name: str
    adapter_detected: str | None
    bank_name: str | None
    account_meta: AccountMetaOut | None
    existing_account_id: str | None
    similar_accounts: list[SimilarAccountOut] = Field(default_factory=list)
    transaction_count: int = 0
    duplicate_count_estimate: int = 0
    parse_warnings: list[str] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)


class ImportConfirmRequest(BaseModel):
    """confirm 시 multipart form 의 ``payload`` 필드(JSON 문자열)로 전송한다."""

    account_id: str | None = None
    create_account: AccountCreate | None = None
    on_duplicate: str = "skip"


class ImportResultOut(BaseModel):
    upload_log_id: str
    account_id: str
    bank_key: str | None
    imported_count: int
    duplicate_count: int
    error_count: int
    status: str
    errors: list[dict[str, Any]] = Field(default_factory=list)
