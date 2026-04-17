import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    department: str | None = None
    role: str = "viewer"


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    department: str | None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: str | None = None
    department: str | None = None
    role: str | None = None
    is_active: bool | None = None
