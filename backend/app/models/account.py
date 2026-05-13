"""계좌 모델 — 일반/외화/대출/기보보증대출 등 다양한 계좌 유형 지원.

확장 메모 (마이그레이션 007):
- account_type: general | foreign | loan | guaranteed_loan (애플리케이션 enum 검증).
- currency(3): ISO 4217. 기본 'KRW'. 무중단 마이그레이션 위해 server_default 사용.
- current_balance: 마지막 업로드 잔액 캐시. 정합성은 last_synced_at 기준.
- account_label: "외화", "대출", "기보보증대출" 등 UI 배지용 라벨.
- alias: 사용자 별칭. 검색은 alias OR account_holder OR account_number 로.
"""
from decimal import Decimal
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Numeric, String, text

from app.models.base import Base, TimestampMixin, UUIDMixin


class Account(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    bank_name = Column(String, nullable=False)
    account_number = Column(String, unique=True, nullable=False)
    account_holder = Column(String, nullable=False)
    business_registration_no = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    # 마이그레이션 007: 계좌 메타 확장.
    account_type = Column(String, nullable=True)  # general | foreign | loan | guaranteed_loan
    # HIGH-6: server_default 는 SQL 표현식이어야 함. raw "KRW" 는 컬럼명으로 해석되어
    # 마이그레이션 007 의 text("'KRW'") 와 diff 가 생긴다.
    currency = Column(String(3), nullable=False, server_default=text("'KRW'"))
    current_balance = Column(Numeric(15, 2), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    account_label = Column(String, nullable=True)
    alias = Column(String, nullable=True)
