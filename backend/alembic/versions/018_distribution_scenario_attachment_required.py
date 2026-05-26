"""T9 distribution_scenarios.attachment_required 컬럼 추가.

목적 (T9 — 2026-05-26):
- 시나리오 단위로 "이 대화는 엑셀/이미지 등 첨부가 권장된다" 마커.
- VIP 프로모션 같은 시나리오는 메시지 본문에 숫자를 직접 노출하지 않고
  엑셀 첨부로 전달 — 검수 UI 에 배너 표시하여 첨부 누락 방지.

idempotent: ADD COLUMN IF NOT EXISTS.
"""
from alembic import op


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_scenarios "
        "ADD COLUMN IF NOT EXISTS attachment_required BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_scenarios DROP COLUMN IF EXISTS attachment_required"
    )
