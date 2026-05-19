"""playground 영속화 보강 — task_id/status/file_path/cost_usd 컬럼 추가.

목적 (사용자 요구사항 #1~#7, 2026-05-19):
- 미디어 새로고침 시 사라지지 않게 (DB row + 디스크 보관)
- 모델별/사용자별 사용량 추적 (cost_usd 컬럼)
- 세션은 이미 영속화 됨 — 사이드바 화면만 추가하면 됨

변경:
- playground_media.url: NOT NULL → NULL 허용 (task 생성 시점에는 url 없음)
- playground_media.task_id: 추가 (unique). 텐센트 task 식별.
- playground_media.model_key: 추가 ("Kling:2.1" 등 ModelName:Version 합성 키)
- playground_media.status: 추가 ("pending"|"running"|"succeeded"|"failed")
- playground_media.error_message: 추가
- playground_media.file_path: 추가 (백엔드 디스크 영구 보관 경로)
- playground_media.cost_usd: 추가
- playground_media.expires_at: 추가 (텐센트 임시 URL 만료 시각)
- playground_messages.cost_usd: 추가
"""
from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # playground_media 보강 -------------------------------------------------
    op.alter_column(
        "playground_media",
        "url",
        existing_type=sa.String(),
        nullable=True,
    )
    op.add_column(
        "playground_media",
        sa.Column("task_id", sa.String(length=200), nullable=True),
    )
    op.create_unique_constraint(
        "uq_playground_media_task_id", "playground_media", ["task_id"]
    )
    op.add_column(
        "playground_media",
        sa.Column("model_key", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "playground_media",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "playground_media",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "playground_media",
        sa.Column("file_path", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "playground_media",
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
    )
    op.add_column(
        "playground_media",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 조회 빈도 높은 컬럼 인덱스 — DESC 정렬은 raw SQL (alembic op.create_index 는
    # 표현식 인덱스 호환성이 부족해서 137 OOM kill 사고 발생한 적 있음 2026-05-19).
    op.execute(
        "CREATE INDEX ix_playground_media_user_created "
        "ON playground_media (user_id, created_at DESC)"
    )
    op.create_index(
        "ix_playground_media_status",
        "playground_media",
        ["status"],
    )

    # playground_messages 보강 ---------------------------------------------
    op.add_column(
        "playground_messages",
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
    )
    op.create_index(
        "ix_playground_messages_model",
        "playground_messages",
        ["model"],
    )


def downgrade() -> None:
    op.drop_index("ix_playground_messages_model", table_name="playground_messages")
    op.drop_column("playground_messages", "cost_usd")

    op.drop_index("ix_playground_media_status", table_name="playground_media")
    op.drop_index("ix_playground_media_user_created", table_name="playground_media")
    op.drop_column("playground_media", "expires_at")
    op.drop_column("playground_media", "cost_usd")
    op.drop_column("playground_media", "file_path")
    op.drop_column("playground_media", "error_message")
    op.drop_column("playground_media", "status")
    op.drop_column("playground_media", "model_key")
    op.drop_constraint(
        "uq_playground_media_task_id", "playground_media", type_="unique"
    )
    op.drop_column("playground_media", "task_id")
    op.alter_column(
        "playground_media",
        "url",
        existing_type=sa.String(),
        nullable=False,
    )
