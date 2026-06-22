from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class UserStatus(str, Enum):
    """가입 승인 상태. 셀프 가입=pending, 관리자 승인=active, 거절=rejected.
    is_active(관리자 사후 정지 토글)와는 별개 축."""

    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"


STATUS_LABELS: dict[str, str] = {
    UserStatus.PENDING.value: "승인대기",
    UserStatus.ACTIVE.value: "활성",
    UserStatus.REJECTED.value: "거절",
}


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
    # T8 트랙: AI Playground (LLM 채팅 + 이미지/영상 생성).
    # 2026-05-19: 일반 직원 접근 가능. 통계만 admin 전용 (별도 PLAYGROUND_USAGE 모듈).
    PLAYGROUND = "playground"
    # T8 통계 대시보드 — admin only. 모델별/사용자별 토큰·비용 집계.
    PLAYGROUND_USAGE = "playground_usage"
    # T8 관리자 — 전 사용자 세션/메시지 열람. admin only.
    PLAYGROUND_ADMIN_SESSIONS = "playground_admin_sessions"
    # T8 관리자 — 백엔드 로그 tail. admin only.
    PLAYGROUND_LOGS = "playground_logs"
    # T9 트랙: 신사업유통 텔레그램 대화 자동화 (T9 PRD).
    # 신사업팀 + admin 접근. 검수/페르소나 관리 등 세부 권한은 라우터 단 require_admin 으로 추가 게이팅.
    DISTRIBUTION = "distribution"
    # PR-E #1: 문서 토큰/비용 사용량 패널 — admin only. ALL_MODULES 로 admin 만 자동 부여.
    # 백엔드 권위는 GET /api/documents/admin/usage 의 require_admin(403).
    DOCUMENTS_ADMIN_USAGE = "documents_admin_usage"
