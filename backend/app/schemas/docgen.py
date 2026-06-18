"""요구 기반 문서 생성 스키마."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["제안서", "계획서", "보고서", "일반"]


class DocGenRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=4000, description="작성 요구/주제")
    doc_type: DocType = "일반"
    use_nas: bool = Field(default=True, description="NAS 벡터검색(RAG)으로 회사 자료 참고")
    limit: int = Field(default=8, ge=0, le=20, description="RAG로 가져올 참고 청크 수")


class DocSection(BaseModel):
    heading: str
    body: str


class DocSourceRef(BaseModel):
    path: str
    score: float


class DocGenResponse(BaseModel):
    title: str
    sections: list[DocSection]
    markdown: str
    sources: list[DocSourceRef]
    cost_usd: float
    model: str


class DocRenderRequest(BaseModel):
    """초안(수정 가능)을 .docx로 렌더."""

    title: str = Field(min_length=1, max_length=200)
    sections: list[DocSection] = Field(min_length=1)
