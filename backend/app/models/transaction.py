from sqlalchemy import Column, Date, ForeignKey, Numeric, String, Text

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
    matched_transaction_id = Column("matched_transaction_id", ForeignKey("transactions.id"), nullable=True)
    match_status = Column(String, default="unmatched")  # unmatched | matched | manual
    memo = Column(Text, nullable=True)
    upload_log_id = Column("upload_log_id", ForeignKey("upload_logs.id"), nullable=True)
