"""체험단 번역 모듈 Pydantic 스키마 (업무개선요구사항 #17)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ReviewTranslationCreate(BaseModel):
    """POST /api/review-translations/translate 요청 본문."""

    source_text: str = Field(min_length=1, max_length=20_000, description="중국어 원문")
    campaign: str | None = Field(default=None, max_length=200, description="캠페인명")
    reviewer_name: str | None = Field(default=None, max_length=100, description="체험단명")
    platform: str | None = Field(default=None, max_length=50, description="플랫폼(샤오홍슈/웨이보 등)")


class ReviewTranslationUpdate(BaseModel):
    """PUT /api/review-translations/{id} 요청 본문. 모든 필드 옵션."""

    translated_text: str | None = Field(default=None, min_length=1, max_length=20_000)
    campaign: str | None = Field(default=None, max_length=200)
    reviewer_name: str | None = Field(default=None, max_length=100)
    platform: str | None = Field(default=None, max_length=50)


class ReviewTranslationRead(BaseModel):
    """단건 응답 스키마. 모델 ORM 객체를 직접 직렬화."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None
    source_text: str
    translated_text: str
    campaign: str | None
    reviewer_name: str | None
    platform: str | None
    model_used: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None
    created_by_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ReviewTranslationList(BaseModel):
    """페이지네이션 응답."""

    items: list[ReviewTranslationRead]
    total: int
    page: int
    page_size: int
