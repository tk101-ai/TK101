from app.models.user import User
from app.modules.constants import Department, Module, UserRole

# All modules currently defined in the system. New modules added here.
ALL_MODULES: list[str] = [m.value for m in Module]

# Department -> accessible modules. Used for non-admin role users.
# Future: replace with permission table; this remains the default fallback.
# NAS_SEARCH 모듈은 전 직원에게 부여(전사 자료 검색용 PoC).
# FORM_FILLER (T5 트랙)도 전 직원에게 부여 — 범용 문서 자동 작성기는 부서 무관 인프라.
DEPARTMENT_MODULES: dict[str, list[str]] = {
    Department.ADMIN.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        # T8 PLAYGROUND: admin only (require_admin 으로 한 번 더 게이팅).
        Module.PLAYGROUND.value,
        # T9 DISTRIBUTION: admin + 신사업팀 사용. 세부 작업은 라우터 단 게이팅.
        Module.DISTRIBUTION.value,
    ],
    Department.FINANCE.value: [
        Module.DASHBOARD.value,
        Module.FINANCE.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        Module.PLAYGROUND.value,
    ],
    Department.MARKETING_1.value: [
        Module.DASHBOARD.value,
        Module.MARKETING_SNS.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        # 체험단 번역: 마케팅1팀(현대아울렛 등 체험단 운영) 주관.
        Module.REVIEW_TRANSLATION.value,
        Module.PLAYGROUND.value,
    ],
    Department.MARKETING_2.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        Module.PLAYGROUND.value,
    ],
    Department.NEW_BUSINESS.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        # T9 트랙 — 신사업팀 주관 모듈 (라이브 1차 2계정 → 점진 확장).
        Module.DISTRIBUTION.value,
        Module.PLAYGROUND.value,
    ],
    Department.NEW_MEDIA.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        Module.PLAYGROUND.value,
    ],
    Department.DESIGN.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
        Module.PLAYGROUND.value,
    ],
}


# ── 부서→모듈 grant 캐시 (DB department_module_grants 를 메모리로) ─────────
# get_user_modules 는 동기 함수로 매 요청 인가에 쓰이므로 DB 왕복 없이 캐시를
# 읽는다. 기동 시(lifespan) load_grants_cache() 로 채우고, 관리자가 grant 를
# 변경하면 다시 호출해 갱신. 캐시 미로딩 시 하드코딩 DEPARTMENT_MODULES 폴백.
_GRANTS_CACHE: dict[str, set[str]] | None = None


async def load_grants_cache() -> None:
    """department_module_grants 테이블 → 메모리 캐시. 기동/grant 변경 시 호출."""
    global _GRANTS_CACHE
    from sqlalchemy import select

    from app.database import async_session
    from app.models.department_module_grant import DepartmentModuleGrant

    async with async_session() as db:
        rows = (await db.execute(select(DepartmentModuleGrant))).scalars().all()
    cache: dict[str, set[str]] = {}
    for r in rows:
        cache.setdefault(r.department, set()).add(r.module)
    _GRANTS_CACHE = cache


def _modules_for_department(dept: str) -> set[str]:
    if _GRANTS_CACHE is not None:
        return set(_GRANTS_CACHE.get(dept, set()))
    return set(DEPARTMENT_MODULES.get(dept, []))  # 캐시 로딩 전 폴백


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
