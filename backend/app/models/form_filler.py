"""T5 범용 문서 자동 작성기 모델 (SQLAlchemy 2.0 mapped_column 스타일).

PRD 6.1 스키마 직역. enum 문자열은 alembic 005_form_filler.py와 정확히 일치.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ----- enum SQL 타입 (alembic이 생성. ORM은 create_type=False로 충돌 방지) -----

FormFileFormatType = ENUM(
    "docx",
    "xlsx",
    "hwpx",
    "pdf_form",
    name="form_file_format",
    create_type=False,
)

FormJobStatusType = ENUM(
    "analyzing",
    "collecting",
    "mapping",
    "reviewing",
    "completed",
    "failed",
    name="form_job_status",
    create_type=False,
)

FormSourceKindType = ENUM(
    "nas_file",
    "user_upload",
    "user_input",
    "web_search",
    name="form_source_kind",
    create_type=False,
)

FormChangeTypeType = ENUM(
    "manual_edit",
    "regenerate",
    "user_filled",
    "lock",
    "unlock",
    name="form_change_type",
    create_type=False,
)


class FormTemplate(Base):
    """양식 라이브러리. file_hash가 캐시 키이자 UNIQUE."""

    __tablename__ = "form_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(FormFileFormatType, nullable=False)
    # variables: [{key, label, type, location, required, default}]
    variables: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    department_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    owner_dept: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FormJob(Base):
    """작성 잡. status 흐름: analyzing → collecting → mapping → reviewing → completed."""

    __tablename__ = "form_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(FormJobStatusType, nullable=False)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    total_tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    langfuse_trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FormDataSource(Base):
    """잡에 등록된 자료 1건. nas_file_id는 T2 nas_files 참조."""

    __tablename__ = "form_data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(FormSourceKindType, nullable=False)
    nas_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nas_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    upload_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # T2 nas_text_chunks.id 배열. FK 미설정(application 레벨 검증).
    nas_chunk_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FormMapping(Base):
    """양식 변수 ↔ 자료 매핑. CHECK 제약이 환각 방어 핵심."""

    __tablename__ = "form_mappings"
    __table_args__ = (
        CheckConstraint(
            "value IS NULL OR source_id IS NOT NULL",
            name="form_mappings_value_requires_source",
        ),
        UniqueConstraint(
            "job_id", "variable_key", name="uq_form_mappings_job_variable"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    variable_key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_data_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FormRevision(Base):
    """검수 변경 이력 (감사 추적). 매핑 생성 후 수정·재생성·잠금 모두 기록."""

    __tablename__ = "form_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    variable_key: Mapped[str] = mapped_column(Text, nullable=False)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(FormChangeTypeType, nullable=False)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
