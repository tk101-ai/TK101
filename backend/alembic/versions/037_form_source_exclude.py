"""form data source per-source exclude

form_data_sources 에 is_excluded 컬럼 추가.
- 사용자가 노이즈/관련없는 자료를 매핑·채우기 입력에서 끄는 용도(개별 제외).
- 제외해도 잡 상세 목록에는 계속 노출되어 다시 포함 가능.
- nullable=False, server_default false (기존 행은 모두 포함 상태로 유지).

Revision ID: 037
Revises: 036
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "form_data_sources",
        sa.Column(
            "is_excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("form_data_sources", "is_excluded")
