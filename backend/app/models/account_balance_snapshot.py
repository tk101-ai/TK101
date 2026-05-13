"""계좌 잔액 스냅샷 모델 — 일자별 잔액 시계열.

스키마 메모:
- (account_id, snapshot_date) UNIQUE: 같은 날 중복 스냅샷 차단.
- 계좌 삭제 시 CASCADE: 잔액 시계열도 함께 삭제.
- currency 기본값 'KRW'. 외화 계좌는 계좌 통화와 일치시켜야 함 (애플리케이션 책임).
- updated_at 없음 — 스냅샷은 immutable. 잘못 등록되면 삭제 후 재등록.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AccountBalanceSnapshot(Base):
    """계좌 잔액 1일 스냅샷."""

    __tablename__ = "account_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "snapshot_date", name="uq_balance_snapshots_account_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # HIGH-6: server_default 는 SQL 표현식이어야 함. raw "KRW" 는 컬럼명으로 해석된다.
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="KRW",
        server_default=text("'KRW'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
