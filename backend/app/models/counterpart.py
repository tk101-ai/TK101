"""거래처(Counterpart) 마스터 모델.

스키마 메모:
- name(200): 정식 상호명. 사용자 검색 진입점.
- aliases: 이전 상호/약칭/영문명 등 다중값. ARRAY(String) 사용. 부분 검색 빈도 높아지면 GIN 인덱스 추가.
- business_registration_no(20): 사업자등록번호. 하이픈 포함 13~14자 가정. 미입력 허용.
- default_category_id: 거래처 → 카테고리 자동 매핑용 기본값. 카테고리 삭제 시 SET NULL.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.category import Category


class Counterpart(Base):
    """거래처(매입처/매출처) 마스터 1건."""

    __tablename__ = "counterparts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    business_registration_no: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    default_category: Mapped["Category | None"] = relationship(
        "Category",
        back_populates="default_for_counterparts",
    )
