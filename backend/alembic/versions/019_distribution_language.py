"""T9 distribution language 컬럼 추가 (시나리오/세션).

목적 (T9 — 2026-05-27):
- 신사업유통 대화 언어를 시나리오/세션 단위로 선택·기록한다.
- distribution_scenarios.language: 'ko'(한국어) | 'zh'(간체 중국어).
  주간/자동 생성 경로가 이 컬럼 값으로 대화 언어를 결정한다.
- distribution_sessions.language: 생성된 세션의 실제 언어를 기록 (검수 UI 표시용).

기본값은 'ko' — 기존 데이터 하위호환 보존.
idempotent: ADD COLUMN IF NOT EXISTS.
"""
from alembic import op


revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_scenarios "
        "ADD COLUMN IF NOT EXISTS language VARCHAR(5) NOT NULL DEFAULT 'ko'"
    )
    op.execute(
        "ALTER TABLE distribution_sessions "
        "ADD COLUMN IF NOT EXISTS language VARCHAR(5) NOT NULL DEFAULT 'ko'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_sessions DROP COLUMN IF EXISTS language"
    )
    op.execute(
        "ALTER TABLE distribution_scenarios DROP COLUMN IF EXISTS language"
    )
