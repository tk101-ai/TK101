"""면장(통관신고) 전용 Pydantic 스키마 (Priority 4).

별도 파일에 둔 이유 (distribution_b2.py 와 동일 정책):
- 공용 ``schemas/distribution.py`` 수정 시 회귀 위험이 커서 면장 흐름은 격리.

엔드포인트 매핑:
- POST /api/distribution/customs/upload  → CustomsUploadResult
- GET  /api/distribution/customs/         → CustomsListResponse
- GET  /api/distribution/customs/summary  → CustomsSummaryOut
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CustomsDeclarationOut(BaseModel):
    """면장 1행 조회 응답."""

    id: uuid.UUID
    company_label: str | None
    bl_number: str | None
    declaration_number: str | None
    product: str | None
    # declared_price(신고가): 실가의 75% 로 신고된 금액.
    declared_price: Decimal | None
    # actual_price(실가): declared_price / 0.75 역산값.
    actual_price: Decimal | None
    currency: str | None
    stock_qty: int | None
    declared_at: date | None
    source_file: str | None
    imported_at: datetime

    model_config = {"from_attributes": True}


class CustomsPreviewRow(BaseModel):
    """업로드 직후 미리보기 행 (DB 저장 전 파싱 결과)."""

    declaration_number: str | None = None
    product: str | None = None
    bl_number: str | None = None
    declared_price: Decimal | None = None
    actual_price: Decimal | None = None
    currency: str | None = None
    stock_qty: int | None = None
    declared_at: date | None = None


class CustomsUploadResult(BaseModel):
    """면장 엑셀 업로드 결과 요약."""

    file_name: str
    company_label: str | None = None
    parsed: int = 0
    inserted: int = 0
    updated: int = 0
    preview: list[CustomsPreviewRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CustomsListResponse(BaseModel):
    """면장 목록 (페이지네이션)."""

    items: list[CustomsDeclarationOut]
    total: int
    limit: int
    offset: int


class CustomsSummaryOut(BaseModel):
    """면장 집계 — 신고가 합 vs 실가(역산) 합."""

    count: int
    total_declared: Decimal
    total_actual: Decimal
    # 역산 비율 (UI 안내용). 기본 0.75.
    declare_ratio: float
