from sqlalchemy import Boolean, Column, String

from app.models.base import Base, TimestampMixin, UUIDMixin


class Account(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    bank_name = Column(String, nullable=False)
    account_number = Column(String, unique=True, nullable=False)
    account_holder = Column(String, nullable=False)
    business_registration_no = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
