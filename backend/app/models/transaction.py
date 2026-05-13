"""거래 모델 — 입출금 기록 + 카테고리/거래처/태그/첨부 + soft delete.

확장 메모 (마이그레이션 007):
- transaction_hash(64): SHA256 hex. (account_id, hash) partial UNIQUE 로 중복 업로드 차단.
  파셜 UNIQUE 인덱스라 NULL 다수 허용 → backfill 단계적 진행 가능.
- category_id, counterpart_id: 분류/거래처 FK. 삭제 시 SET NULL.
- tags ARRAY(String): 자유 태그. GIN 인덱스는 빈도 보고 추후.
- attachment_url: 영수증/증빙 파일 경로 (S3 키 또는 로컬 path).
- is_deleted: soft delete. 활성 거래 조회는 partial index 사용 (ix_transactions_is_deleted_false).
"""
from sqlalchemy import Boolean, Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Transaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transactions"

    account_id = Column("account_id", ForeignKey("accounts.id"), nullable=False)
    transaction_date = Column(Date, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    balance = Column(Numeric(15, 2), nullable=True)
    counterpart_name = Column(String, nullable=True)
    description = Column(String, nullable=True)
    transaction_type = Column(String, nullable=False)  # deposit | withdrawal
    matched_transaction_id = Column(
        "matched_transaction_id", ForeignKey("transactions.id"), nullable=True
    )
    match_status = Column(String, default="unmatched")  # unmatched | matched | manual
    memo = Column(Text, nullable=True)
    upload_log_id = Column(
        "upload_log_id", ForeignKey("upload_logs.id"), nullable=True
    )

    # 마이그레이션 007: 중복 방지 + 분류 FK + 태그/첨부 + soft delete.
    transaction_hash = Column(String(64), nullable=True)
    category_id = Column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    counterpart_id = Column(
        ForeignKey("counterparts.id", ondelete="SET NULL"), nullable=True
    )
    tags = Column(ARRAY(String), nullable=True)
    attachment_url = Column(String, nullable=True)
    is_deleted = Column(Boolean, nullable=False, server_default="false")

    category = relationship("Category", foreign_keys=[category_id])
    counterpart = relationship("Counterpart", foreign_keys=[counterpart_id])
