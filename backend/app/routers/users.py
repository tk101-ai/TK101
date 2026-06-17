from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.modules.constants import UserStatus
from app.schemas.auth import PasswordResetRequest
from app.schemas.user import (
    DepartmentStat,
    UserApprove,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.auth import hash_password
from app.services.department_sync import set_user_departments

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


def _dept_values(primary: str, extras) -> list[str]:
    """주 부서 + 추가 부서 → user_departments 동기화용 값 리스트."""
    out = [primary]
    for d in extras or []:
        out.append(d.value if isinstance(d, Enum) else d)
    return out


@router.get("", response_model=list[UserRead])
async def list_users(
    status_filter: UserStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(User.status == status_filter.value)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats", response_model=list[DepartmentStat])
async def department_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User.department, func.count().label("count"))
        .where(User.is_active.is_(True))
        .group_by(User.department)
    )
    return [DepartmentStat(department=row.department, count=row.count) for row in result.all()]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
        department=body.department.value,
        role=body.role.value,
        status=UserStatus.ACTIVE.value,  # 관리자 생성은 즉시 활성
    )
    db.add(user)
    await db.flush()
    await set_user_departments(db, user.id, _dept_values(body.department.value, body.departments))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/approve", response_model=UserRead)
async def approve_user(user_id: str, body: UserApprove, db: AsyncSession = Depends(get_db)):
    """가입 승인 — 부서·역할 확정 후 active 전환."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")
    user.status = UserStatus.ACTIVE.value
    user.role = body.role.value
    user.department = body.department.value
    user.is_active = True
    await set_user_departments(db, user.id, _dept_values(body.department.value, body.departments))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/reject", response_model=UserRead)
async def reject_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """가입 거절 — rejected + 비활성."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")
    user.status = UserStatus.REJECTED.value
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: str,
    body: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """관리자 강제 비번 reset. current_password 검증 없이 새 해시로 교체."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return None


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 자기 자신의 역할/활성/상태 변경 차단(관리자 lockout·권한 사고 방지).
    if str(current_user.id) == user_id:
        if body.role is not None and body.role.value != current_user.role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="자신의 역할은 변경할 수 없습니다")
        if body.is_active is not None and body.is_active != current_user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="자신의 계정은 비활성화할 수 없습니다")
        if body.status is not None and body.status.value != current_user.status:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="자신의 상태는 변경할 수 없습니다")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = body.model_dump(exclude_unset=True)
    new_departments = data.pop("departments", None)  # 관계 → 스칼라 setattr 제외
    for field, value in data.items():
        if isinstance(value, Enum):
            value = value.value
        setattr(user, field, value)
    if new_departments is not None:
        await set_user_departments(db, user.id, _dept_values(user.department, new_departments))
    await db.commit()
    await db.refresh(user)
    return user
