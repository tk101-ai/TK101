"""distribution scenario — 사용자 자유 텍스트 지시(instruction) 컬럼

코드 beats 대신 사용자가 자연어로 작성한 지시문으로 대화를 생성하기 위한 컬럼.
- instruction 이 있으면 scenario_engine 이 그 텍스트를 흐름 가이드로 주입.
- beats 는 비어 있어도 동작 (문장은 매번 LLM 이 새로 생성).
- 저장형(사용자 시나리오) + 즉석(ad-hoc, active=False) 모두 이 컬럼 사용.

Revision ID: 027
Revises: 026
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "distribution_scenarios",
        sa.Column("instruction", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("distribution_scenarios", "instruction")
