"""sns comment translation cache

social_post_comments 에 translated_text 컬럼 추가.
- 조회 시 번역(다국어→한국어) 결과를 캐시해 재번역 비용을 막는다.
- 원문(text)은 그대로 보존. NULL 이면 아직 번역하지 않은 댓글.

Revision ID: 029
Revises: 028
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "social_post_comments",
        sa.Column("translated_text", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("social_post_comments", "translated_text")
