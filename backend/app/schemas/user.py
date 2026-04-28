import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.modules.constants import Department, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    department: Department
    role: UserRole = UserRole.MEMBER


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    department: Department
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserMe(UserRead):
    modules: list[str]


class UserUpdate(BaseModel):
    name: str | None = None
    department: Department | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class DepartmentStat(BaseModel):
    department: Department
    count: int
