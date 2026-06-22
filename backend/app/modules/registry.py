import logging

from app.models.user import User
from app.modules.constants import Module, UserRole

logger = logging.getLogger(__name__)

# All modules currently defined in the system. New modules added here.
ALL_MODULES: list[str] = [m.value for m in Module]


# ── 부서→모듈 grant 캐시 (DB department_module_grants 를 메모리로) ─────────
# 권한 진실원천은 DB ``department_module_grants`` 단일소스다(P0-1, 동적설계).
# get_user_modules 는 동기 함수로 매 요청 인가에 쓰이므로 DB 왕복 없이 메모리
# 캐시를 읽는다. 기동 시(lifespan) load_grants_cache() 로 채우고, 관리자가 grant 를
# 변경하면 다시 호출해 갱신한다.
#
# 과거에는 하드코딩 ``DEPARTMENT_MODULES`` 폴백 매트릭스가 있었으나, DB grants 와
# 이중 진실원천이 되어 divergence 위험(예: 운영 DB 의 marketing_2 가 폴백과 달라짐)이
# 있었고 CLAUDE.md 동적설계 원칙에 위배되어 제거했다. 운영 DB grants 가 모든 부서를
# 커버함을 확인했다(2026-06-22). 기동 시 verify_grants_cache() 로 누락을 loud 검증한다.
#
# 캐시 미로딩(DB 일시 장애 등) 시에는 하드코딩 매핑으로 조용히 폴백하지 않는다 —
# 대신 loud 경고를 남기고 DASHBOARD 최소권한만 부여한다(get_user_modules 의 빈집합
# 기본값). 이는 잘못된(낡은) 인가를 흘리는 것보다 안전한 선택이다.
_GRANTS_CACHE: dict[str, set[str]] | None = None
# 캐시 미로딩 상태에서 인가가 호출될 때 로그 폭주를 막기 위한 1회성 경고 플래그.
_WARNED_CACHE_MISSING: bool = False


async def load_grants_cache() -> None:
    """department_module_grants 테이블 → 메모리 캐시. 기동/grant 변경 시 호출."""
    global _GRANTS_CACHE, _WARNED_CACHE_MISSING
    from sqlalchemy import select

    from app.database import async_session
    from app.models.department_module_grant import DepartmentModuleGrant

    async with async_session() as db:
        rows = (await db.execute(select(DepartmentModuleGrant))).scalars().all()
    cache: dict[str, set[str]] = {}
    for r in rows:
        cache.setdefault(r.department, set()).add(r.module)
    _GRANTS_CACHE = cache
    _WARNED_CACHE_MISSING = False  # 로드 성공 → 경고 플래그 리셋


def grants_cache_loaded() -> bool:
    """grant 캐시가 비어있지 않게 로드됐는지 (기동 검증/헬스용)."""
    return bool(_GRANTS_CACHE)


async def verify_grants_cache() -> list[str]:
    """기동 시 grant 진실원천 검증. 누락 부서 목록을 반환(비면 정상).

    실제 사용자가 소속된 모든 부서(users.department ∪ user_departments)에 대해
    DB grant 가 하나라도 있는지 확인한다. 없으면 그 부서 사용자는 DASHBOARD 만
    받게 되므로(lockout 위험) loud ERROR 로 보고하고 호출자가 대응하게 한다.

    캐시는 호출 전에 load_grants_cache() 로 채워져 있어야 한다.
    """
    from sqlalchemy import select

    from app.database import async_session
    from app.models.user import User as UserModel
    from app.models.user_department import UserDepartment

    departments: set[str] = set()
    async with async_session() as db:
        primary = (
            await db.execute(
                select(UserModel.department).where(UserModel.department.isnot(None))
            )
        ).scalars().all()
        extra = (
            await db.execute(select(UserDepartment.department))
        ).scalars().all()
    departments.update(d for d in primary if d)
    departments.update(d for d in extra if d)

    cache = _GRANTS_CACHE or {}
    missing = sorted(d for d in departments if not cache.get(d))
    return missing


def _modules_for_department(dept: str) -> set[str]:
    global _WARNED_CACHE_MISSING
    if _GRANTS_CACHE is not None:
        return set(_GRANTS_CACHE.get(dept, set()))
    # 캐시 미로딩 — 하드코딩 폴백 없이 loud 경고 후 빈집합(상위에서 DASHBOARD 보정).
    if not _WARNED_CACHE_MISSING:
        logger.error(
            "권한 grant 캐시 미로딩 — DB 단일소스 인가 불가. "
            "load_grants_cache() 가 기동 시 실패했을 수 있음. "
            "비admin 사용자는 임시로 DASHBOARD 만 접근 가능. DB/기동 로그 확인 필요."
        )
        _WARNED_CACHE_MISSING = True
    return set()


def _user_departments(user: User) -> set[str]:
    """사용자의 전체 소속 부서(주 부서 + user_departments)."""
    depts: set[str] = set()
    if getattr(user, "department", None):
        depts.add(user.department)
    try:
        for ud in (user.departments or []):  # lazy="selectin" → 이미 eager load
            depts.add(ud.department)
    except Exception:
        pass  # detached 등 예외 시 주 부서만
    return depts


def get_user_modules(user: User) -> list[str]:
    """접근 가능 모듈 키. admin=전체, 그 외=소속 부서들의 grant 합집합."""
    if user.role == UserRole.ADMIN.value:
        return list(ALL_MODULES)
    mods: set[str] = set()
    for dept in _user_departments(user):
        mods |= _modules_for_department(dept)
    if not mods:
        mods = {Module.DASHBOARD.value}
    return sorted(mods)


def user_has_module(user: User, module: str) -> bool:
    return module in get_user_modules(user)
