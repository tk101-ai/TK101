"""카테고리 모델 — 3단계 트리 (depth <= 3, DB CHECK 제약).

스키마 메모:
- parent_id self FK, ON DELETE SET NULL → 상위 카테고리 삭제 시 하위는 고아 노드로 남고 운영자가 재배치.
- code UNIQUE: 회계 분류 코드(예: "5100") 등 외부 매핑용. 없어도 됨.
- color "#RRGGBB" 7자: UI 배지. 검증은 라우터 단에서 정규식.
- depth 1 = 대분류, 2 = 중분류, 3 = 소분류. 마이그레이션 007에서 CHECK 제약 강제.
- children/parent 관계는 동일 테이블 self-reference. backref 대신 명시 relationship.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.counterpart import Counterpart


class Category(Base):
    """수입/지출 카테고리 (3단계 트리)."""

    __tablename__ = "categories"
    __table_args__ = (CheckConstraint("depth <= 3", name="categories_depth_max_3"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # self-reference: 부모/자식.
    parent: Mapped["Category | None"] = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list["Category"]] = relationship(
        "Category",
        back_populates="parent",
        cascade="save-update",
    )

    # counterparts.default_category_id 역참조.
    default_for_counterparts: Mapped[list["Counterpart"]] = relationship(
        "Counterpart",
        back_populates="default_category",
    )
