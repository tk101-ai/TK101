"""거래처(Counterpart) Pydantic 스키마.

설계 메모:
- aliases: list[str] | None. 빈 리스트도 None 으로 정규화 권장 (서비스 레이어 책임).
- business_registration_no: 최대 20자. 검증(체크썸)은 서비스 레이어에서.
- CounterpartList: 페이지네이션 응답 봉투. items/total/page/page_size 표준.
- MergeRequest / MatchRequest·MatchResponse: 거래처 통합·자동매칭 액션 전용.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CounterpartBase(BaseModel):
    name: str = Field(..., max_length=200)
    aliases: list[str] | None = None
    business_registration_no: str | None = Field(default=None, max_length=20)
    default_category_id: uuid.UUID | None = None


class CounterpartCreate(CounterpartBase):
    pass


class CounterpartUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    aliases: list[str] | None = None
    business_registration_no: str | None = Field(default=None, max_length=20)
    default_category_id: uuid.UUID | None = None


class CounterpartRead(CounterpartBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CounterpartList(BaseModel):
    """페이지네이션 응답."""

    items: list[CounterpartRead]
    total: int
    page: int
    page_size: int


class CounterpartMergeRequest(BaseModel):
    """POST /api/counterparts/merge 요청 본문.

    source_id 의 거래내역/별칭을 target_id 로 이전 후 source 삭제.
    """

    source_id: uuid.UUID
    target_id: uuid.UUID


MatchType = Literal["exact_business_no", "exact_name", "alias", "none"]


class CounterpartMatchRequest(BaseModel):
    """POST /api/counterparts/match 요청 본문 — 거래처 자동 매칭 조회."""

    name: str = Field(..., max_length=200)
    business_registration_no: str | None = Field(default=None, max_length=20)


class CounterpartMatchResponse(BaseModel):
    """매칭 결과 — None 이면 신규 등록 후보."""

    counterpart_id: uuid.UUID | None
    match_type: MatchType
