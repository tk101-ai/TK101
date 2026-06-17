from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_department import UserDepartment


async def set_user_departments(db: AsyncSession, user_id, dept_values: list[str]) -> None:
    """사용자의 user_departments 를 주어진 부서 집합으로 교체.

    주 부서(users.department)를 반드시 포함해서 호출할 것. 중복 제거.
    commit 은 호출측 책임.
    """
    await db.execute(delete(UserDepartment).where(UserDepartment.user_id == user_id))
    seen: set[str] = set()
    for d in dept_values:
        if d and d not in seen:
            seen.add(d)
            db.add(UserDepartment(user_id=user_id, department=d))
