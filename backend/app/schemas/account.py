import uuid
from datetime import datetime

from pydantic import BaseModel


class AccountCreate(BaseModel):
    bank_name: str
    account_number: str
    account_holder: str
    business_registration_no: str | None = None


class AccountRead(BaseModel):
    id: uuid.UUID
    bank_name: str
    account_number: str
    account_holder: str
    business_registration_no: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountUpdate(BaseModel):
    bank_name: str | None = None
    account_number: str | None = None
    account_holder: str | None = None
    business_registration_no: str | None = None
    is_active: bool | None = None
