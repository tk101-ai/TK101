"""sns post manual category (구분)

social_posts 에 수동 구분(카테고리) 컬럼 추가.
- SNS API 로는 못 긁어오는 분류 축을 사용자가 직접 태그한다.
- 값: 행사 / 기획 / 정책 / 이벤트 / 기타 (애플리케이션 레이어 enum, DB 는 가변 문자열).
- category: NULL 이면 미분류. nullable, 사용자 설정.

Revision ID: 035
Revises: 034
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "social_posts",
        sa.Column("category", sa.String(length=16), nullable=True),
    )


def downgrade():
    op.drop_column("social_posts", "category")
