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
- playground_media.cost_usd: 이미 존재 (008/009) → skip
- playground_media.expires_at: 추가
- playground_messages.cost_usd: 추가

idempotent:
- IF NOT EXISTS 패턴을 적극 사용 (이미 적용된 컬럼은 건너뜀).
- 첫 배포가 부분 실패해도 재실행 안전.
"""
from alembic import op


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # playground_media 보강 -------------------------------------------------
    # url 을 nullable 로 (task 생성 시점엔 결과 URL 없음).
    op.execute("ALTER TABLE playground_media ALTER COLUMN url DROP NOT NULL")

    # 컬럼 추가 — IF NOT EXISTS (PostgreSQL 9.6+) 로 멱등성 보장.
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS task_id VARCHAR(200)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_playground_media_task_id "
        "ON playground_media (task_id)"
    )
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS model_key VARCHAR(100)"
    )
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS status VARCHAR(20) "
        "NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS error_message TEXT"
    )
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS file_path VARCHAR(500)"
    )
    # cost_usd 는 이미 존재 — IF NOT EXISTS 로 skip.
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10, 6)"
    )
    op.execute(
        "ALTER TABLE playground_media ADD COLUMN IF NOT EXISTS expires_at "
        "TIMESTAMP WITH TIME ZONE"
    )

    # 인덱스 — DESC 정렬은 raw SQL.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_playground_media_user_created "
        "ON playground_media (user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_playground_media_status "
        "ON playground_media (status)"
    )

    # playground_messages 보강 ---------------------------------------------
    op.execute(
        "ALTER TABLE playground_messages ADD COLUMN IF NOT EXISTS cost_usd "
        "NUMERIC(12, 6)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_playground_messages_model "
        "ON playground_messages (model)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_playground_messages_model")
    op.execute("ALTER TABLE playground_messages DROP COLUMN IF EXISTS cost_usd")

    op.execute("DROP INDEX IF EXISTS ix_playground_media_status")
    op.execute("DROP INDEX IF EXISTS ix_playground_media_user_created")
    op.execute("ALTER TABLE playground_media DROP COLUMN IF EXISTS expires_at")
    # cost_usd 는 008/009 이미 정의되어 있어 014 의 downgrade 에서 건드리지 않음.
    op.execute("ALTER TABLE playground_media DROP COLUMN IF EXISTS file_path")
    op.execute("ALTER TABLE playground_media DROP COLUMN IF EXISTS error_message")
    op.execute("ALTER TABLE playground_media DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE playground_media DROP COLUMN IF EXISTS model_key")
    op.execute("DROP INDEX IF EXISTS uq_playground_media_task_id")
    op.execute("ALTER TABLE playground_media DROP COLUMN IF EXISTS task_id")
    # url 은 운영 데이터가 NULL 이면 NOT NULL 복원이 불가능 → 그대로 둠.
