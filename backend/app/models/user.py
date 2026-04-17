from sqlalchemy import Boolean, Column, String

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)
    role = Column(String, nullable=False, default="viewer")
    is_active = Column(Boolean, default=True)
