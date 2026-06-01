"""distribution session — 그룹 송신용 group_chat_id 컬럼

3명 방(2 API 계정 + 관리자 수동참여) 지원:
- group_chat_id 가 설정되면 세션의 모든 메시지를 1:1 DM 이 아니라
  해당 텔레그램 그룹(chat)에 게시한다. 각 메시지는 발신 페르소나의
  클라이언트로 그룹에 전송되고, 관리자는 그 그룹 멤버로 수동 참여한다.
- NULL 이면 기존 1:1 DM 송신(하위호환).

Revision ID: 028
Revises: 027
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "distribution_sessions",
        sa.Column("group_chat_id", sa.String(length=64), nullable=True),
    )


def downgrade():
    op.drop_column("distribution_sessions", "group_chat_id")
