from sqlalchemy import Boolean, Column, Numeric, String, text

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    department = Column(String, nullable=False)
    role = Column(String, nullable=False, default="member")
    is_active = Column(Boolean, default=True)
    # T8 Playground 월 한도 (USD). 이번 월 누적 cost_usd 가 이 값을 넘으면
    # /chat·/image·/video 진입 시 402. admin 만 변경 가능.
    monthly_quota_usd = Column(
        Numeric(10, 2), nullable=False, server_default=text("10.00")
    )
