"""review_translations table (체험단 중→한 번역, 업무개선요구사항 #17)

Revision ID: 006
Revises: 005
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_translations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("translated_text", sa.Text, nullable=False),
        sa.Column("campaign", sa.String(200), nullable=True),
        sa.Column("reviewer_name", sa.String(100), nullable=True),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "created_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # 목록 조회 정렬용 (최신순). 008+에서 더 늘어나면 부분 인덱스 검토.
    op.execute(
        "CREATE INDEX ix_review_translations_created_at_desc "
        "ON review_translations (created_at DESC)"
    )
    op.create_index(
        "ix_review_translations_campaign", "review_translations", ["campaign"]
    )
    op.create_index(
        "ix_review_translations_created_by_id",
        "review_translations",
        ["created_by_id"],
    )


def downgrade():
    op.drop_index(
        "ix_review_translations_created_by_id", table_name="review_translations"
    )
    op.drop_index(
        "ix_review_translations_campaign", table_name="review_translations"
    )
    op.execute("DROP INDEX IF EXISTS ix_review_translations_created_at_desc")
    op.drop_table("review_translations")
