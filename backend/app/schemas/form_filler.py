"""T5 범용 문서 자동 작성기 Pydantic v2 스키마.

PRD 7.3 API 스펙의 입출력 DTO. enum 값은 alembic/모델과 동일 문자열 유지.
T5-B(라우터/서비스), T5-C(프론트엔드 API 클라이언트)가 함께 import.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ----- enum 리터럴 (DB enum 문자열과 정확히 일치) -----

FormFileFormat = Literal["docx", "xlsx", "hwpx", "pdf_form"]

FormJobStatus = Literal[
    "analyzing",
    "collecting",
    "mapping",
    "reviewing",
    "completed",
    "failed",
]

FormSourceKind = Literal["nas_file", "user_upload", "user_input", "web_search"]

FormChangeType = Literal[
    "manual_edit",
    "regenerate",
    "user_filled",
    "lock",
    "unlock",
]

FormVariableType = Literal["text", "number", "date", "boolean", "currency", "table_row"]


# ----- 공용 building blocks -----


class FormVariable(BaseModel):
    """양식 변수 정의 (form_templates.variables JSONB 내부)."""

    key: str = Field(min_length=1, max_length=100, description="템플릿 내 변수 키")
    label: str = Field(min_length=1, max_length=200, description="표시 이름")
    type: FormVariableType = "text"
    location: str | None = Field(
        default=None, description="문서 내 위치 힌트 (paragraph #, cell A2 등)"
    )
    required: bool = True
    default: Any | None = None


# ----- form_templates -----


class FormTemplateBase(BaseModel):
    """라이브러리 저장 시 공통 입력 필드."""

    name: str = Field(min_length=1, max_length=200)
    department_tags: list[str] | None = None
    owner_dept: str | None = None


class FormTemplateAnalyzeResponse(BaseModel):
    """`/api/forms/templates/analyze` 응답 — 캐시 hit/miss 공통."""

    template_id: uuid.UUID
    cached: bool = Field(description="True면 file_hash 캐시 hit")
    file_format: FormFileFormat
    variables: list[FormVariable]


class FormTemplateUpdateRequest(BaseModel):
    """검수 1회 후 변수 라벨/타입 보정용 PATCH 요청."""

    name: str | None = None
    department_tags: list[str] | None = None
    owner_dept: str | None = None
    variables: list[FormVariable] | None = None
    is_active: bool | None = None


class FormTemplateRead(FormTemplateBase):
    """라이브러리 검색·상세 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    file_hash: str
    file_path: str
    file_format: FormFileFormat
    variables: list[FormVariable]
    usage_count: int
    is_active: bool
    is_deleted: bool
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None


# ----- form_jobs -----


class FormJobCreateRequest(BaseModel):
    """잡 생성 (template_id 없으면 임시 양식 직접 업로드 흐름)."""

    template_id: uuid.UUID | None = None
    department: str | None = None


class FormJobRead(BaseModel):
    """잡 상세."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID | None = None
    user_id: uuid.UUID
    department: str | None = None
    status: FormJobStatus
    output_path: str | None = None
    cost_usd: Decimal = Decimal("0")
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    langfuse_trace_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class FormJobListItem(BaseModel):
    """목록용 경량 DTO."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID | None = None
    department: str | None = None
    status: FormJobStatus
    created_at: datetime
    completed_at: datetime | None = None


# ----- form_data_sources -----


class FormDataSourceUploadResponse(BaseModel):
    """사용자 업로드 자료 등록 결과."""

    source_id: uuid.UUID
    kind: FormSourceKind
    upload_path: str | None = None
    extracted_chars: int = 0


class FormDataSourceNasRequest(BaseModel):
    """NAS 검색 결과에서 선택한 자료를 잡에 추가."""

    nas_file_id: uuid.UUID
    nas_chunk_ids: list[uuid.UUID] = Field(default_factory=list)


class FormDataSourceUserInputRequest(BaseModel):
    """누락 보강 단계 — 사용자가 직접 입력한 텍스트를 자료로 등록."""

    variable_key: str
    text: str = Field(min_length=1)


class FormDataSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    kind: FormSourceKind
    nas_file_id: uuid.UUID | None = None
    upload_path: str | None = None
    nas_chunk_ids: list[uuid.UUID] | None = None
    extracted_text: str | None = None
    created_at: datetime


# ----- form_mappings -----


class FormMappingRead(BaseModel):
    """매핑 행. value가 채워졌으면 source_id 필수 (DB CHECK)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    variable_key: str
    value: str | None = None
    source_id: uuid.UUID | None = None
    source_excerpt: str | None = None
    llm_confidence: Decimal | None = None
    reasoning: str | None = None
    manual_override: bool = False
    confirmed: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class FormMappingManualEditRequest(BaseModel):
    """검수 단계 사용자 직접 수정. value를 채우려면 source_id 동봉 필수."""

    value: str | None = None
    source_id: uuid.UUID | None = None
    source_excerpt: str | None = None
    confirmed: bool | None = None


class FormMappingRegenerateRequest(BaseModel):
    """1개 변수만 Haiku 4.5로 재생성."""

    feedback_comment: str | None = Field(default=None, max_length=2000)


# ----- form_revisions -----


class FormRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    variable_key: str
    previous_value: str | None = None
    new_value: str | None = None
    change_type: FormChangeType
    feedback_comment: str | None = None
    changed_by: uuid.UUID | None = None
    changed_at: datetime


# ----- 종합 응답 (검수 화면용) -----


class FormJobDetailResponse(BaseModel):
    """검수 화면 렌더용 한 방 응답: 잡 + 매핑 + 자료 묶음."""

    job: FormJobRead
    mappings: list[FormMappingRead]
    sources: list[FormDataSourceRead]
    template: FormTemplateRead | None = None
