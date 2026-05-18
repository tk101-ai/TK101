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
    NAS_SEARCH = "nas_search"
    # T5 트랙: 범용 문서 자동 작성기 (PRD T5_범용문서자동작성기 FR-10).
    # MVP 단계는 P-AI 1명 + 검수 강제 모델, 부서 cap은 Phase 2.
    FORM_FILLER = "form_filler"
    # 업무개선요구사항 #17: 현대아울렛 체험단 중→한 번역 자동저장 모듈.
    # 마케팅1팀(주관) + 관리자만 접근. Haiku 4.5 라우팅 (NFR-02 비용 절감).
    REVIEW_TRANSLATION = "review_translation"
    # T8 트랙: AI Playground (Phase 1 — Claude 채팅, Phase 4~5 미디어 확장).
    # admin only 정책 (T8 PRD 7절). DEPARTMENT_MODULES 매핑은 일반 부서에 부여하지 않음.
    PLAYGROUND = "playground"
    # T9 트랙: 신사업유통 텔레그램 대화 자동화 (T9 PRD).
    # 신사업팀 + admin 접근. 검수/페르소나 관리 등 세부 권한은 라우터 단 require_admin 으로 추가 게이팅.
    DISTRIBUTION = "distribution"
