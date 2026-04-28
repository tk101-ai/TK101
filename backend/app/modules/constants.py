from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class Department(str, Enum):
    MARKETING_1 = "marketing_1"
    MARKETING_2 = "marketing_2"
    NEW_BUSINESS = "new_business"
    FINANCE = "finance"
    NEW_MEDIA = "new_media"
    DESIGN = "design"
    ADMIN = "admin"


DEPARTMENT_LABELS: dict[str, str] = {
    Department.MARKETING_1.value: "마케팅1팀",
    Department.MARKETING_2.value: "마케팅2팀",
    Department.NEW_BUSINESS.value: "신사업팀",
    Department.FINANCE.value: "재무팀",
    Department.NEW_MEDIA.value: "뉴미디어팀",
    Department.DESIGN.value: "디자인팀",
    Department.ADMIN.value: "관리자",
}


class Module(str, Enum):
    DASHBOARD = "dashboard"
    FINANCE = "finance"
    USERS = "users"
    MARKETING_SNS = "marketing_sns"
