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
    ],
    Department.FINANCE.value: [
        Module.DASHBOARD.value,
        Module.FINANCE.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
    ],
    Department.MARKETING_1.value: [
        Module.DASHBOARD.value,
        Module.MARKETING_SNS.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
    ],
    Department.MARKETING_2.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
    ],
    Department.NEW_BUSINESS.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
    ],
    Department.NEW_MEDIA.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
    ],
    Department.DESIGN.value: [
        Module.DASHBOARD.value,
        Module.NAS_SEARCH.value,
        Module.FORM_FILLER.value,
    ],
}


def get_user_modules(user: User) -> list[str]:
    """Return module keys the user can access.

    role=admin grants every module regardless of department.
    role=member uses department mapping; unknown department falls back to dashboard only.
    """
    if user.role == UserRole.ADMIN.value:
        return list(ALL_MODULES)
    return list(DEPARTMENT_MODULES.get(user.department, [Module.DASHBOARD.value]))


def user_has_module(user: User, module: str) -> bool:
    return module in get_user_modules(user)
