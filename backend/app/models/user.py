from sqlalchemy import Boolean, Column, Numeric, String, text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    department = Column(String, nullable=False)  # 주 부서(하위호환). 추가 부서는 user_departments.
    role = Column(String, nullable=False, default="member")
    is_active = Column(Boolean, default=True)
    # 가입 승인 상태. 셀프 가입은 pending 으로 생성, 관리자 승인 시 active.
    # is_active 와 별개 축(is_active=관리자 사후 정지 토글).
    status = Column(String, nullable=False, server_default=text("'active'"))
    # T8 Playground 월 한도 (USD). 이번 월 누적 cost_usd 가 이 값을 넘으면
    # /chat·/image·/video 진입 시 402. admin 만 변경 가능.
    monthly_quota_usd = Column(
        Numeric(10, 2), nullable=False, server_default=text("10.00")
    )

    # 다중부서 소속(주 부서 포함). lazy="selectin" → 매 user 로드 시 자동 eager load
    # 하여 동기 함수(get_user_modules)에서 async lazy-load 없이 안전하게 읽힌다.
    departments = relationship(
        "UserDepartment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
