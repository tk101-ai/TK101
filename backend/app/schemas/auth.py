from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.constants import Department


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """직원 셀프 회원가입. role 은 서버가 member 고정(권한상승 방지),
    status 는 pending 으로 생성되어 관리자 승인 전 로그인 불가."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    department: Department

    @field_validator("password")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        if v != v.strip() or any(ch.isspace() for ch in v):
            raise ValueError("비밀번호에 공백을 포함할 수 없습니다")
        return v


class PasswordChangeRequest(BaseModel):
    """본인 비밀번호 변경 요청. current_password 로 신원 재확인 후 new_password 적용."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        # 공백을 허용하면 의도치 않은 trailing space 비번이 생기므로 보수적으로 차단.
        if v != v.strip() or any(ch.isspace() for ch in v):
            raise ValueError("새 비밀번호에 공백을 포함할 수 없습니다")
        return v


class PasswordResetRequest(BaseModel):
    """관리자 강제 reset 요청. 현재 비번 검증 없이 신규 해시로 교체."""

    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        if v != v.strip() or any(ch.isspace() for ch in v):
            raise ValueError("새 비밀번호에 공백을 포함할 수 없습니다")
        return v
