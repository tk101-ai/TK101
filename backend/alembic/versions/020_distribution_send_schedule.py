"""T9 예약 송신 스케줄 컬럼 추가 (distribution_messages).

목적 (T9 — 2026-05-27):
- 승인 + 예약 시각(scheduled_start)이 지정된 세션을 백그라운드 워커가
  실시간(30초 cap 없음)으로 자동 송신할 수 있도록 메시지별 절대 송신 예정 시각과
  멱등 송신 상태 머신을 영속화한다.

추가 컬럼 (distribution_messages):
- scheduled_send_at TIMESTAMPTZ NULL
    = 세션 scheduled_start + 직전까지 메시지 send_after_sec 누적합.
    워커는 ``scheduled_send_at <= now()`` 인 메시지만 due 로 픽업.
- sent_at TIMESTAMPTZ NULL
    (이미 모델/스키마에 존재하나, 일부 구배포 누락 대비 idempotent 추가).
- send_state VARCHAR(16) NOT NULL DEFAULT 'pending'
    pending|sending|sent|failed|skipped. 워커가 'pending' → 'sending' 으로
    원자적 claim 후 송신 → 재시작·동시성 환경에서 중복 송신 차단.

세션 status 는 plain VARCHAR(20) 컬럼이라 Postgres ENUM 이 아님 → 별도 enum
마이그레이션 불필요. 'scheduled' / 'sending' 값은 애플리케이션 레벨에서만 사용.

idempotent: ADD COLUMN IF NOT EXISTS (migration 019 패턴과 동일).
"""
from alembic import op


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS scheduled_send_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS send_state VARCHAR(16) NOT NULL DEFAULT 'pending'"
    )
    # 워커 due 탐색 쿼리 (send_state='pending' AND scheduled_send_at <= now()) 가속.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_distribution_messages_send_state_due "
        "ON distribution_messages (send_state, scheduled_send_at)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_distribution_messages_send_state_due"
    )
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS send_state"
    )
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS scheduled_send_at"
    )
    # sent_at 은 워커 도입 이전부터 모델에 존재하던 컬럼이므로 downgrade 에서 보존.
