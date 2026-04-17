from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class UploadLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "upload_logs"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    upload_type = Column(String, nullable=False)  # transaction | tax_invoice
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True)
    row_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_detail = Column(JSONB, nullable=True)
    status = Column(String, nullable=False, default="processing")
