from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class UserDepartment(UUIDMixin, TimestampMixin, Base):
    """사용자 ↔ 부서 다대다. 일반사원은 1행, 팀장급↑은 여러 부서 소속 가능.

    users.department(단일)는 '주 부서'로 보존(하위호환). 모듈 권한 계산은
    users.department ∪ user_departments 의 합집합으로 한다(registry.get_user_modules).
    """

    __tablename__ = "user_departments"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "department", name="uq_user_department"),
    )
