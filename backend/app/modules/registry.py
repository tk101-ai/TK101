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
