"""요구 기반 문서 생성 스키마."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocType = Literal["제안서", "계획서", "보고서", "일반"]

# 출처 모드 — 회사 NAS RAG만 / 사용자 업로드만 / 둘다.
SourceMode = Literal["rag", "uploaded", "both"]


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
    # 표시용 파일명(있으면 path 꼬리 대신 노출). NAS=file_name, 업로드=업로드 파일명.
    name: str | None = None
    # 출처 구분: "nas"(회사 NAS RAG) / "uploaded"(사용자 업로드).
    source_type: str = "nas"
    # NAS 문서 단위 식별자(doc_id). 업로드 자료는 빈 문자열.
    doc_id: str | None = None


class DocGenResponse(BaseModel):
    title: str
    sections: list[DocSection]
    markdown: str
    sources: list[DocSourceRef]
    # cost_usd 는 관리자 전용(GET /api/documents/admin/usage)이라 응답에서 제외.
    model: str
    # 영속화된 문서 id(재열람 키). 저장 실패 시 None.
    document_id: str | None = None


class DocgenDocumentBrief(BaseModel):
    """내 문서 목록 항목(가벼운 메타만)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    doc_type: str | None = None
    created_at: datetime


class DocgenDocumentDetail(BaseModel):
    """재열람용 전체 문서(섹션/출처 포함)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    sections: list[DocSection] = Field(default_factory=list)
    sources: list[DocSourceRef] = Field(default_factory=list)
    topic: str | None = None
    doc_type: str | None = None
    source_mode: str | None = None
    created_at: datetime


class DocRenderRequest(BaseModel):
    """초안(수정 가능)을 .docx로 렌더."""

    title: str = Field(min_length=1, max_length=200)
    sections: list[DocSection] = Field(min_length=1)


class DocSectionRegenResponse(BaseModel):
    section: DocSection
    model: str


class DocSectionReview(BaseModel):
    heading: str
    grounded: bool = True
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class DocReviewResponse(BaseModel):
    overall_score: int
    summary: str
    section_reviews: list[DocSectionReview] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    model: str
