"""요구 기반 문서 생성 스키마."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
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
    # LLM 이 실제 인용했다고 보고한 자료 여부. False 여도 생성 시 컨텍스트로는 주입됨.
    cited: bool = False


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


class ThemeOverride(BaseModel):
    """디자인 프리셋이 담는 테마(편집가능 .pptx/.docx 색·폰트). 빈 항목은 회사 기본."""

    palette_primary: str | None = None  # '#RRGGBB'
    palette_accent: str | None = None
    palette_text: str | None = None
    heading_font: str | None = None
    body_font: str | None = None


class DocRenderRequest(BaseModel):
    """초안(수정 가능)을 .docx/.pptx로 렌더. theme 가 있으면 그 색·폰트로."""

    title: str = Field(min_length=1, max_length=200)
    sections: list[DocSection] = Field(min_length=1)
    theme: ThemeOverride | None = None


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


# ---------------------------------------------------------------------------
# 리터치 프롬프트(=디자인/내용 프리셋)
# ---------------------------------------------------------------------------

# target: 어떤 AI용으로 다듬을지. general=도구비종속, internal=우리 generator용.
RetouchTarget = Literal["general", "gamma", "gpt", "gemini", "internal"]


class RetouchPromptRequest(BaseModel):
    """현재 초안(편집 가능 상태)으로 리터치 프롬프트 생성."""

    title: str = Field(min_length=1, max_length=300)
    sections: list[DocSection] = Field(min_length=1)
    doc_type: DocType = "일반"
    topic: str | None = Field(default=None, max_length=4000)
    target: RetouchTarget = "general"
    # 이 프롬프트를 만들어낸 원본 문서 id(있으면 프리셋 저장 시 연결).
    source_document_id: str | None = None


class RetouchPromptOut(BaseModel):
    """생성된 리터치 프롬프트 본문."""

    prompt_text: str
    target: RetouchTarget
    model: str


class RetouchPresetSaveRequest(BaseModel):
    """디자인 프리셋 저장 — 프롬프트 또는 테마(또는 둘 다)."""

    title: str = Field(min_length=1, max_length=300)
    prompt_text: str = Field(default="")
    doc_type: DocType | None = None
    target: RetouchTarget = "general"
    source_document_id: str | None = None
    # 테마(편집가능 .pptx/.docx 색·폰트).
    palette_primary: str | None = None
    palette_accent: str | None = None
    palette_text: str | None = None
    heading_font: str | None = None
    body_font: str | None = None


class RetouchPresetPatchRequest(BaseModel):
    """프리셋 수정 — 제목/본문/테마 편집 또는 공유 토글. 보낸 필드만 반영."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    prompt_text: str | None = None
    is_shared: bool | None = None
    palette_primary: str | None = None
    palette_accent: str | None = None
    palette_text: str | None = None
    heading_font: str | None = None
    body_font: str | None = None


class RetouchPresetOut(BaseModel):
    """디자인 프리셋 1행(프롬프트 + 테마)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    doc_type: str | None = None
    target: str
    prompt_text: str
    palette_primary: str | None = None
    palette_accent: str | None = None
    palette_text: str | None = None
    heading_font: str | None = None
    body_font: str | None = None
    is_shared: bool = False
    shared_at: datetime | None = None
    source_document_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SharedRetouchPresetOut(RetouchPresetOut):
    """공유 프리셋 1행 — 소유자 표기 포함."""

    owner_name: str | None = None
    owner_department: str | None = None
    is_mine: bool = False


class HtmlDeckRequest(BaseModel):
    """디자인 프롬프트 + 콘텐츠 → HTML 슬라이드 덱 생성."""

    title: str = Field(min_length=1, max_length=300)
    sections: list[DocSection] = Field(min_length=1)
    doc_type: DocType = "일반"
    # 디자인 시스템(보통 리터치 프리셋의 prompt_text).
    design_prompt: str = Field(min_length=1)


class HtmlDeckOut(BaseModel):
    """생성된 HTML 덱 + 비용."""

    html: str
    model: str
    cost_usd: Decimal
