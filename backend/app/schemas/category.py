"""카테고리 Pydantic 스키마.

설계 메모:
- CategoryTree: 자기 참조 응답 모델. children: list[CategoryTree] 로 트리 직렬화.
- depth 는 서버에서 parent 기반으로 자동 계산 (Create/Update 입력 금지).
- DB CHECK (depth <= 3) 가 최종 가드. 서비스 레이어에서 사전 검증.
- color: "#RRGGBB" 7자 정규식. 잘못된 입력 422 응답.

스키마 분리 이유:
- CategoryBase: 클라이언트가 보낼 수 있는 공통 필드(이름·부모·코드·색상)만 포함.
- CategoryRead: Base + 서버 계산 필드(id, depth, timestamps).
- CategoryCreate/Update: depth 미포함 → 라우터에서 compute_depth() 로 계산.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    """클라이언트 입력 공통 필드 (Create/Update 가 상속)."""

    name: str = Field(..., max_length=100)
    parent_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryCreate(CategoryBase):
    """POST /api/categories — depth 는 서버에서 계산."""

    pass


class CategoryUpdate(BaseModel):
    """PATCH /api/categories/{id} — 모든 필드 옵션. depth 는 서버 재계산."""

    name: str | None = Field(default=None, max_length=100)
    parent_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryRead(CategoryBase):
    """단건 응답 — Base + 서버 계산 필드."""

    id: uuid.UUID
    depth: int = Field(ge=1, le=3)
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CategoryTree(CategoryRead):
    """트리 응답: children 재귀 포함."""

    children: list["CategoryTree"] = Field(default_factory=list)


CategoryTree.model_rebuild()
