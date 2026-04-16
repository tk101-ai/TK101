"""Domain 예외 계층.

Design Ref: §6.3 Exception Hierarchy

비즈니스 규칙 위반을 표현. Presentation 레이어의 미들웨어가
이를 HTTP 응답으로 매핑 (Sprint 1+에서 구현).
"""


class DomainException(Exception):
    """비즈니스 규칙 위반의 기본 클래스.

    Attributes:
        code: 에러 코드 (API 응답에 노출)
        http_status: 매핑할 HTTP 상태 코드
        message: 사용자 친화적 메시지
        details: 추가 상세 정보 (dict)
    """

    code: str = "DOMAIN_ERROR"
    http_status: int = 400

    def __init__(
        self,
        message: str = "",
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidCredentialsError(DomainException):
    """로그인 자격증명 불일치."""

    code = "INVALID_CREDENTIALS"
    http_status = 401


class UnauthorizedError(DomainException):
    """인증 누락/만료."""

    code = "UNAUTHORIZED"
    http_status = 401


class ForbiddenError(DomainException):
    """권한 부족 (인증은 되었으나 접근 불가)."""

    code = "FORBIDDEN"
    http_status = 403


class NotFoundError(DomainException):
    """리소스 미존재."""

    code = "NOT_FOUND"
    http_status = 404


class DuplicateError(DomainException):
    """중복 데이터 (unique constraint 위반 등)."""

    code = "CONFLICT"
    http_status = 409


class ValidationError(DomainException):
    """도메인 수준의 입력 검증 실패.

    Pydantic 검증(400 VALIDATION_ERROR)과는 구분 — 이는 비즈니스 규칙 위반.
    """

    code = "VALIDATION_ERROR"
    http_status = 400
