"""사용자 월 한도 (monthly_quota_usd) 컬럼 추가.

목적 (T8 Playground 백엔드 확장 — 2026-05-19):
- 사용자별 월 한도(USD)를 DB 단에서 강제. POST /chat·/image·/video 진입 시
  ``check_quota_or_raise`` 가 이 컬럼을 읽어 한도 초과 시 402.
- 기본 10.00 USD. 관리자 화면에서 사용자별로 변경 가능
  (PUT /api/playground/admin/users/{id}/quota).

idempotent:
- ``ADD COLUMN IF NOT EXISTS`` 사용. 부분 실패 후 재실행 안전.
- downgrade 도 ``DROP COLUMN IF EXISTS``.
"""
from alembic import op


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS monthly_quota_usd "
        "NUMERIC(10, 2) NOT NULL DEFAULT 10.00"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS monthly_quota_usd")
