from pydantic import BaseModel

from app.modules.constants import Department


class DepartmentGrants(BaseModel):
    """부서 → 허용 모듈 목록."""

    department: Department
    modules: list[str]


class GrantsUpdate(BaseModel):
    """해당 부서의 허용 모듈 전체 교체(set)."""

    modules: list[str]
