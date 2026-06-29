"""playground_media 참고(소스) 이미지 링크

i2v(image-to-video) 영상이 어떤 이미지로 만들어졌는지 표시하기 위해
source_media_id(같은 테이블의 이미지 row) 를 추가. 소스 삭제 시 NULL.

Revision ID: 042
Revises: 041
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "playground_media",
        sa.Column(
            "source_media_id",
            UUID(as_uuid=True),
            sa.ForeignKey("playground_media.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("playground_media", "source_media_id")
