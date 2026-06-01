"""sns post comments — 소유/관리 계정 게시물 댓글 본문 저장

Meta(FB Page / IG Business) 게시물의 댓글 본문을 수집해 저장.
(post_id, external_comment_id) UNIQUE 로 재수집 멱등.

Revision ID: 026
Revises: 025
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_post_comments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("social_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_comment_id", sa.String, nullable=True),
        sa.Column("author", sa.String, nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("commented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("like_count", sa.Integer, nullable=True),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "post_id", "external_comment_id", name="uq_post_comment_external"
        ),
    )
    op.create_index(
        "ix_social_post_comments_post_id", "social_post_comments", ["post_id"]
    )
    op.create_index(
        "ix_social_post_comments_external_comment_id",
        "social_post_comments",
        ["external_comment_id"],
    )


def downgrade():
    op.drop_index(
        "ix_social_post_comments_external_comment_id",
        table_name="social_post_comments",
    )
    op.drop_index(
        "ix_social_post_comments_post_id", table_name="social_post_comments"
    )
    op.drop_table("social_post_comments")
