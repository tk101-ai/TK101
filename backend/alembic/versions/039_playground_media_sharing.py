"""playground media 공유 (콘텐츠 라이브러리)

playground_media 에 공유 컬럼 추가.
- is_shared: True 면 playground 모듈 사용자 전체에게 공유 갤러리로 노출. 소유자만 토글.
- shared_at: 공유로 켠 시각(공유 갤러리 정렬 기준). 공유 해제 시 NULL.
- nullable=False, server_default false (기존 행은 모두 비공개 유지).
- 공유 갤러리 조회용 부분 인덱스: 공유 + 성공 상태만 빠르게 최신순 정렬.

Revision ID: 039
Revises: 038
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "playground_media",
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "playground_media",
        sa.Column(
            "shared_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # 공유 갤러리: is_shared=true 행만, shared_at 최신순 조회. 부분 인덱스로 경량화.
    op.create_index(
        "ix_playground_media_shared",
        "playground_media",
        ["shared_at"],
        unique=False,
        postgresql_where=sa.text("is_shared"),
    )


def downgrade():
    op.drop_index("ix_playground_media_shared", table_name="playground_media")
    op.drop_column("playground_media", "shared_at")
    op.drop_column("playground_media", "is_shared")
