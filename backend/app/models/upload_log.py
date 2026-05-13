"""업로드 로그 모델 — 거래내역/세금계산서 등 업로드 1건 추적.

확장 메모 (마이그레이션 007):
- duplicate_count: 업로드 중 transaction_hash 충돌로 스킵된 건수.
- imported_count: 실제 DB 적재 건수. row_count - duplicate_count - error_count 와 일치해야 함.
- bank_key: 은행 식별자 (kbstar | ibk | nonghyup | shinhan | woori | hana). 거래내역 업로드용.
- period_label: 사용자 표시용 라벨 ("2026-1사분기" 등). 자동 추출 또는 사용자 입력.
"""
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

    # 마이그레이션 007: 진단/통계 메타.
    duplicate_count = Column(Integer, nullable=False, server_default="0")
    imported_count = Column(Integer, nullable=False, server_default="0")
    bank_key = Column(String(20), nullable=True)
    period_label = Column(String(20), nullable=True)
