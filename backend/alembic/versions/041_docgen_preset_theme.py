"""docgen 디자인 프리셋에 테마(색·폰트) 통합

리터치 프롬프트(=디자인 프리셋)가 프롬프트뿐 아니라 테마(색·폰트)도 담아
편집가능 .pptx/.docx 에 적용되게 한다(라이브러리 통합). prompt_text 는 테마만
담는 프리셋을 위해 nullable 기본 '' 로 완화.

Revision ID: 041
Revises: 040
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "docgen_retouch_prompts",
        sa.Column("palette_primary", sa.String(7), nullable=True),
    )
    op.add_column(
        "docgen_retouch_prompts",
        sa.Column("palette_accent", sa.String(7), nullable=True),
    )
    op.add_column(
        "docgen_retouch_prompts",
        sa.Column("palette_text", sa.String(7), nullable=True),
    )
    op.add_column(
        "docgen_retouch_prompts",
        sa.Column("heading_font", sa.String(80), nullable=True),
    )
    op.add_column(
        "docgen_retouch_prompts",
        sa.Column("body_font", sa.String(80), nullable=True),
    )
    # prompt_text: 테마만 담는 프리셋 허용 → server_default '' (기존 행 영향 없음).
    op.alter_column(
        "docgen_retouch_prompts",
        "prompt_text",
        server_default="",
        existing_type=sa.Text(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "docgen_retouch_prompts",
        "prompt_text",
        server_default=None,
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.drop_column("docgen_retouch_prompts", "body_font")
    op.drop_column("docgen_retouch_prompts", "heading_font")
    op.drop_column("docgen_retouch_prompts", "palette_text")
    op.drop_column("docgen_retouch_prompts", "palette_accent")
    op.drop_column("docgen_retouch_prompts", "palette_primary")
