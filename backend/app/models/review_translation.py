"""체험단 후기 중→한 번역 저장 모델 (업무개선요구사항 #17).

목적:
- 현대아울렛 등 중국 체험단(샤오홍슈, 웨이보 등) 후기를 한국어로 번역해 보관.
- Claude Haiku 4.5 라우팅(비용 절감, NFR-02), 결과는 PostgreSQL에 영구 보존.
- 마케팅1팀 + 관리자만 접근 (modules/registry.py).

스키마 메모:
- source_text/translated_text는 길이 제한 없음(Text). 평균 후기 200~600자, 최대 ~3000자 가정.
- cost_usd Numeric(10,6) — 1건 비용은 보통 $0.001 미만이라 소수점 6자리 필요.
- created_by_id는 SET NULL — 사용자 탈퇴 후에도 번역 이력 보존.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReviewTranslation(Base):
    """체험단 후기 중→한 번역 1건."""

    __tablename__ = "review_translations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 원문(중국어). 빈 문자열 차단은 라우터 단에서.
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 번역문(한국어). 사용자 편집 가능.
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 운영 메타 — 옵션이지만 검색 필터에 사용.
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 호출 메타 — 추적/감사용.
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
