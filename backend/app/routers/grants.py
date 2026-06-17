"""부서→모듈 grant 관리 (관리자 전용). 하드코딩 매핑을 런타임 편집으로.

변경 시 registry 의 메모리 캐시를 갱신해 즉시 반영. admin role 은 grant 와
무관하게 전 모듈 접근(get_user_modules)이므로 여기서 admin 부서는 다뤄도 무의미.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.department_module_grant import DepartmentModuleGrant
from app.modules.constants import Department, Module
from app.modules.registry import ALL_MODULES, load_grants_cache
from app.schemas.grants import DepartmentGrants, GrantsUpdate

router = APIRouter(
    prefix="/api/admin/grants",
    tags=["grants"],
    dependencies=[Depends(require_admin)],
)

_VALID_MODULES = {m.value for m in Module}


@router.get("/modules", response_model=list[str])
async def available_modules() -> list[str]:
    """매트릭스 열로 쓸 전체 모듈 키."""
    return list(ALL_MODULES)


@router.get("", response_model=list[DepartmentGrants])
async def list_grants(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(DepartmentModuleGrant))).scalars().all()
    by_dept: dict[str, list[str]] = {}
    for r in rows:
        by_dept.setdefault(r.department, []).append(r.module)
    # 부서 enum 전체를 반환(빈 부서도 행으로).
    return [
        DepartmentGrants(department=d, modules=sorted(by_dept.get(d.value, [])))
        for d in Department
    ]


@router.put("/{department}", response_model=DepartmentGrants)
async def set_grants(
    department: Department,
    body: GrantsUpdate,
    db: AsyncSession = Depends(get_db),
):
    mods = sorted({m for m in body.modules if m in _VALID_MODULES})
    await db.execute(
        delete(DepartmentModuleGrant).where(
            DepartmentModuleGrant.department == department.value
        )
    )
    for m in mods:
        db.add(DepartmentModuleGrant(department=department.value, module=m))
    await db.commit()
    await load_grants_cache()  # 메모리 캐시 즉시 갱신 → 인가에 바로 반영
    return DepartmentGrants(department=department, modules=mods)
