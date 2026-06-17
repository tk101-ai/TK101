import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.modules.constants import Department, UserRole, UserStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    department: Department  # 주 부서
    role: UserRole = UserRole.MEMBER
    # 추가 소속 부서(팀장급 다중부서). 미지정 시 주 부서만.
    departments: list[Department] | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    department: Department
    role: UserRole
    is_active: bool
    status: UserStatus
    created_at: datetime
    # 전체 소속 부서(주 부서 포함). ORM relationship(UserDepartment) → 부서값 변환.
    departments: list[Department] = []

    model_config = {"from_attributes": True}

    @field_validator("departments", mode="before")
    @classmethod
    def _dept_values(cls, v):
        if v is None:
            return []
        return [getattr(item, "department", item) for item in v]


class UserMe(UserRead):
    modules: list[str]


class UserUpdate(BaseModel):
    name: str | None = None
    department: Department | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    status: UserStatus | None = None
    departments: list[Department] | None = None


class UserApprove(BaseModel):
    """관리자 가입 승인. 부서·역할 확정 후 active 전환."""

    department: Department
    role: UserRole = UserRole.MEMBER
    departments: list[Department] | None = None


class DepartmentStat(BaseModel):
    department: Department
    count: int
