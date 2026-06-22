"""sns comment AI summary cache

social_posts 에 댓글 AI 요약 캐시 컬럼 추가.
- analyze 엔드포인트가 계산한 요약을 저장해 새로고침/드로어 재열람 시
  LLM 을 다시 호출하지 않고 즉시 보여준다(비용 절감).
- comment_summary: 요약 본문(NULL 이면 아직 분석 안 함).
- comment_summary_at: 요약을 마지막으로 계산한 시각.

Revision ID: 034
Revises: 033
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "social_posts",
        sa.Column("comment_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "social_posts",
        sa.Column("comment_summary_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("social_posts", "comment_summary_at")
    op.drop_column("social_posts", "comment_summary")
