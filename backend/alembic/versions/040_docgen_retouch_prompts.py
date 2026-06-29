"""docgen 리터치 프롬프트(프리셋) 라이브러리

생성 문서를 다른 AI로 재디자인/재생성할 때 쓰는 고품질 프롬프트를 저장.
개인 보관함 + is_shared 공유 토글(playground_media 공유 패턴 동일).

Revision ID: 040
Revises: 039
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: F401  (대칭성)

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "docgen_retouch_prompts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column(
            "source_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("docgen_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=True),
        sa.Column(
            "target", sa.String(20), nullable=False, server_default="general"
        ),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_docgen_retouch_prompts_user_id",
        "docgen_retouch_prompts",
        ["user_id"],
    )
    # 공유 프리셋 갤러리: is_shared=true 행만 shared_at 최신순. 부분 인덱스.
    op.create_index(
        "ix_docgen_retouch_prompts_shared",
        "docgen_retouch_prompts",
        ["shared_at"],
        postgresql_where=sa.text("is_shared"),
    )


def downgrade():
    op.drop_index(
        "ix_docgen_retouch_prompts_shared", table_name="docgen_retouch_prompts"
    )
    op.drop_index(
        "ix_docgen_retouch_prompts_user_id", table_name="docgen_retouch_prompts"
    )
    op.drop_table("docgen_retouch_prompts")
