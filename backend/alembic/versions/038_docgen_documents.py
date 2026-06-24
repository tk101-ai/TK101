"""docgen documents — 사용자별 생성 문서 영속화 (#1)

docgen /generate 는 무상태였다. 생성 결과(제목/섹션/출처/메타)를 사용자별로
저장해 나중에 다시 열어 재렌더/다운로드/출처 확인할 수 있게 한다.
AI Playground 세션 패턴(per-user, user_id FK CASCADE)을 따른다.

Revision ID: 038
Revises: 037
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "docgen_documents",
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
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("topic", sa.String, nullable=True),
        sa.Column("doc_type", sa.String(50), nullable=True),
        sa.Column("source_mode", sa.String(20), nullable=True),
        sa.Column(
            "sections",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sources", JSONB, nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_docgen_documents_user_id", "docgen_documents", ["user_id"]
    )


def downgrade():
    op.drop_index(
        "ix_docgen_documents_user_id", table_name="docgen_documents"
    )
    op.drop_table("docgen_documents")
