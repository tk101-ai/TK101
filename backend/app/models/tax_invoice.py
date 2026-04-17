from sqlalchemy import Column, Date, ForeignKey, Numeric, String, Text

from app.models.base import Base, TimestampMixin, UUIDMixin


class TaxInvoice(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_invoices"

    invoice_type = Column(String, nullable=False)  # purchase | sales
    invoice_number = Column(String, unique=True, nullable=True)
    issue_date = Column(Date, nullable=False)
    supplier_name = Column(String, nullable=False)
    supplier_biz_no = Column(String, nullable=True)
    buyer_name = Column(String, nullable=True)
    buyer_biz_no = Column(String, nullable=True)
    supply_amount = Column(Numeric(15, 2), nullable=False)
    tax_amount = Column(Numeric(15, 2), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    matched_transaction_id = Column("matched_transaction_id", ForeignKey("transactions.id"), nullable=True)
    match_status = Column(String, default="unmatched")
    memo = Column(Text, nullable=True)
    upload_log_id = Column("upload_log_id", ForeignKey("upload_logs.id"), nullable=True)
