import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class TaxInvoiceRead(BaseModel):
    id: uuid.UUID
    invoice_type: str
    invoice_number: str | None
    issue_date: date
    supplier_name: str
    supplier_biz_no: str | None
    buyer_name: str | None
    buyer_biz_no: str | None
    supply_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    matched_transaction_id: uuid.UUID | None
    match_status: str
    memo: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
