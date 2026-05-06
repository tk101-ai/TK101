"""form filler tables (T5: 범용 문서 자동 작성기)

5개 테이블 + 4개 enum + CHECK 제약(form_mappings.value IS NULL OR source_id IS NOT NULL)으로
환각 방어 핵심 가드레일을 DB 레벨에서 강제한다.

Revision ID: 005
Revises: 004
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


# enum 이름은 PRD 13.1 계약상 변경 금지. T5-B/C/D 트랙이 동일 이름으로 import.
FORM_FILE_FORMAT_NAME = "form_file_format"
FORM_JOB_STATUS_NAME = "form_job_status"
FORM_SOURCE_KIND_NAME = "form_source_kind"
FORM_CHANGE_TYPE_NAME = "form_change_type"

FORM_FILE_FORMAT_VALUES = ("docx", "xlsx", "hwpx", "pdf_form")
FORM_JOB_STATUS_VALUES = (
    "analyzing",
    "collecting",
    "mapping",
    "reviewing",
    "completed",
    "failed",
)
FORM_SOURCE_KIND_VALUES = ("nas_file", "user_upload", "user_input", "web_search")
FORM_CHANGE_TYPE_VALUES = (
    "manual_edit",
    "regenerate",
    "user_filled",
    "lock",
    "unlock",
)


def upgrade():
    # 1. enum 4개 생성. create_type=False로 컬럼 생성 시 재생성 시도하지 않도록 분리.
    form_file_format = ENUM(
        *FORM_FILE_FORMAT_VALUES, name=FORM_FILE_FORMAT_NAME, create_type=False
    )
    form_job_status = ENUM(
        *FORM_JOB_STATUS_VALUES, name=FORM_JOB_STATUS_NAME, create_type=False
    )
    form_source_kind = ENUM(
        *FORM_SOURCE_KIND_VALUES, name=FORM_SOURCE_KIND_NAME, create_type=False
    )
    form_change_type = ENUM(
        *FORM_CHANGE_TYPE_VALUES, name=FORM_CHANGE_TYPE_NAME, create_type=False
    )

    bind = op.get_bind()
    ENUM(*FORM_FILE_FORMAT_VALUES, name=FORM_FILE_FORMAT_NAME).create(bind, checkfirst=True)
    ENUM(*FORM_JOB_STATUS_VALUES, name=FORM_JOB_STATUS_NAME).create(bind, checkfirst=True)
    ENUM(*FORM_SOURCE_KIND_VALUES, name=FORM_SOURCE_KIND_NAME).create(bind, checkfirst=True)
    ENUM(*FORM_CHANGE_TYPE_VALUES, name=FORM_CHANGE_TYPE_NAME).create(bind, checkfirst=True)

    # 2. form_templates: 양식 라이브러리. file_hash 기반 캐시 키.
    op.create_table(
        "form_templates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("file_hash", sa.Text, nullable=False, unique=True),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_format", form_file_format, nullable=False),
        # variables: [{key, label, type, location, required, default}]
        sa.Column("variables", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("department_tags", ARRAY(sa.Text), nullable=True),
        sa.Column("owner_dept", sa.Text, nullable=True),
        sa.Column(
            "usage_count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_deleted", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index("ix_form_templates_file_hash", "form_templates", ["file_hash"])
    op.create_index("ix_form_templates_name", "form_templates", ["name"])
    # GIN: 부서 태그 다중 검색 (department_tags @> ARRAY['CS'] 등)
    op.execute(
        "CREATE INDEX ix_form_templates_department_tags "
        "ON form_templates USING gin (department_tags)"
    )

    # 3. form_jobs: 작성 잡. template_id NULL = 임시 양식.
    op.create_table(
        "form_jobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("form_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("department", sa.Text, nullable=True),
        sa.Column("status", form_job_status, nullable=False),
        sa.Column("output_path", sa.Text, nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_tokens_in",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_tokens_out",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("langfuse_trace_id", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_form_jobs_user_id", "form_jobs", ["user_id"])
    op.create_index("ix_form_jobs_status", "form_jobs", ["status"])
    op.create_index("ix_form_jobs_department", "form_jobs", ["department"])
    op.execute(
        "CREATE INDEX ix_form_jobs_created_at_desc "
        "ON form_jobs (created_at DESC)"
    )

    # 4. form_data_sources: 자료 메타. nas_file_id는 T2 nas_files 참조.
    op.create_table(
        "form_data_sources",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("form_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", form_source_kind, nullable=False),
        sa.Column(
            "nas_file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("nas_files.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("upload_path", sa.Text, nullable=True),
        # nas_chunk_ids: T2 nas_text_chunks.id 배열. FK는 배열에 직접 못 걸어 application 레벨 검증.
        sa.Column("nas_chunk_ids", ARRAY(UUID(as_uuid=True)), nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_form_data_sources_job_id", "form_data_sources", ["job_id"])
    op.create_index("ix_form_data_sources_kind", "form_data_sources", ["kind"])
    op.create_index(
        "ix_form_data_sources_nas_file_id", "form_data_sources", ["nas_file_id"]
    )

    # 5. form_mappings: 양식-자료 매핑. CHECK 제약이 환각 방어 핵심.
    op.create_table(
        "form_mappings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("form_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variable_key", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("form_data_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_excerpt", sa.Text, nullable=True),
        sa.Column("llm_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column(
            "manual_override",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "confirmed", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        # 환각 방어: 값이 채워졌으면 반드시 출처가 있어야 함.
        sa.CheckConstraint(
            "value IS NULL OR source_id IS NOT NULL",
            name="form_mappings_value_requires_source",
        ),
        sa.UniqueConstraint(
            "job_id", "variable_key", name="uq_form_mappings_job_variable"
        ),
    )
    op.create_index("ix_form_mappings_job_id", "form_mappings", ["job_id"])

    # 6. form_revisions: 검수 변경 이력 (감사 추적).
    op.create_table(
        "form_revisions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("form_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variable_key", sa.Text, nullable=False),
        sa.Column("previous_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("change_type", form_change_type, nullable=False),
        sa.Column("feedback_comment", sa.Text, nullable=True),
        sa.Column(
            "changed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_form_revisions_job_id", "form_revisions", ["job_id"])
    op.execute(
        "CREATE INDEX ix_form_revisions_changed_at_desc "
        "ON form_revisions (changed_at DESC)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_form_revisions_changed_at_desc")
    op.drop_index("ix_form_revisions_job_id", table_name="form_revisions")
    op.drop_table("form_revisions")

    op.drop_index("ix_form_mappings_job_id", table_name="form_mappings")
    op.drop_table("form_mappings")

    op.drop_index(
        "ix_form_data_sources_nas_file_id", table_name="form_data_sources"
    )
    op.drop_index("ix_form_data_sources_kind", table_name="form_data_sources")
    op.drop_index("ix_form_data_sources_job_id", table_name="form_data_sources")
    op.drop_table("form_data_sources")

    op.execute("DROP INDEX IF EXISTS ix_form_jobs_created_at_desc")
    op.drop_index("ix_form_jobs_department", table_name="form_jobs")
    op.drop_index("ix_form_jobs_status", table_name="form_jobs")
    op.drop_index("ix_form_jobs_user_id", table_name="form_jobs")
    op.drop_table("form_jobs")

    op.execute("DROP INDEX IF EXISTS ix_form_templates_department_tags")
    op.drop_index("ix_form_templates_name", table_name="form_templates")
    op.drop_index("ix_form_templates_file_hash", table_name="form_templates")
    op.drop_table("form_templates")

    bind = op.get_bind()
    ENUM(name=FORM_CHANGE_TYPE_NAME).drop(bind, checkfirst=True)
    ENUM(name=FORM_SOURCE_KIND_NAME).drop(bind, checkfirst=True)
    ENUM(name=FORM_JOB_STATUS_NAME).drop(bind, checkfirst=True)
    ENUM(name=FORM_FILE_FORMAT_NAME).drop(bind, checkfirst=True)
