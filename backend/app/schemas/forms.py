"""T5 트랙 forms 라우터 응답/요청 스키마.

T5-A 의 schemas.form_filler 가 머지될 때까지 forms 라우터가 사용하는 임시 정의를
라우터 본문에서 분리한 것이다. (동작 동일 — 클래스 정의/필드는 변경하지 않음.)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VariableSchema(BaseModel):
    key: str
    label: str
    type: str = "text"
    location: str = ""
    confidence: float = 0.5
    required: bool = False
    default: str | None = None


class TemplateAnalyzeResponse(BaseModel):
    template_id: uuid.UUID
    file_hash: str
    name: str
    version: int
    variables: list[VariableSchema]
    cache_hit: bool = False
    cost_usd: float = 0.0


class TemplateBrief(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    file_hash: str
    department_tags: list[str] = Field(default_factory=list)
    usage_count: int = 0
    created_at: datetime


class TemplateDetail(TemplateBrief):
    variables: list[VariableSchema]
    file_path: str
    file_format: str = "docx"


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    department_tags: list[str] | None = None
    variables: list[VariableSchema] | None = None


class JobCreateRequest(BaseModel):
    template_id: uuid.UUID
    department: str | None = None


class MappingPayload(BaseModel):
    variable_key: str
    value: str | None
    source_id: uuid.UUID | None
    source_excerpt: str | None
    llm_confidence: float = 0.0
    reasoning: str = ""
    confirmed: bool = False
    manual_override: bool = False


class SourceBrief(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    nas_file_id: uuid.UUID | None = None
    upload_path: str | None = None
    nas_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    extracted_text: str | None = None
    display_name: str | None = None
    created_at: datetime


class JobDetail(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID | None
    template: TemplateDetail | None = None  # frontend nested 접근 (detail.template.name 등)
    sources: list[SourceBrief] = Field(default_factory=list)
    status: str
    department: str | None
    cost_usd: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    langfuse_trace_id: str | None = None
    error_message: str | None = None
    output_path: str | None = None
    mappings: list[MappingPayload] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class NasSourceAttachRequest(BaseModel):
    nas_file_ids: list[uuid.UUID] = Field(default_factory=list)
    nas_paths: list[str] = Field(
        default_factory=list,
        description="NAS 검색결과에서 파일 단위로 선택할 때 경로(payload path) 목록.",
    )
    nas_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    auto_query: str | None = Field(
        default=None,
        description="제공 시 의미 검색으로 chunk_ids 자동 채움. limit는 limit 인자 사용.",
    )
    auto_query_from_template: bool = Field(
        default=False,
        description="True면 auto_query 미지정 시 양식 변수 라벨로 쿼리를 자동 생성해 검색(B2).",
    )
    limit: int = Field(default=20, ge=1, le=50)


class MappingPatchRequest(BaseModel):
    value: str | None = None
    source_id: uuid.UUID | None = None
    source_excerpt: str | None = None
    confirmed: bool | None = None
    feedback_comment: str | None = None


class RegenerateRequest(BaseModel):
    variable_key: str
    user_feedback: str | None = None


class RenderRequest(BaseModel):
    save_to_nas: bool = True


class RevisionPayload(BaseModel):
    id: uuid.UUID
    variable_key: str
    previous_value: str | None
    new_value: str | None
    change_type: str
    feedback_comment: str | None
    changed_at: datetime


class JobStatusUpdate(BaseModel):
    status: str
