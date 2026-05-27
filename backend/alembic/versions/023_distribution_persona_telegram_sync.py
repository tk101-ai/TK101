"""T9 distribution 페르소나 텔레그램 연동 정보 동기화 컬럼.

목적 (T9 — 2026-05-27, 요구사항 2 "발신자 정보 항상 최신화"):
- 발신자(페르소나) 정보가 실제 연동된 텔레그램 계정과 항상 일치하도록,
  로그인/수동 동기화 시점에 get_me() 결과를 페르소나에 반영한다.
- distribution_personas.telegram_username: 연동 계정의 @username 저장.
  display_name 은 기존 컬럼을 get_me() 결과로 갱신 (마이그레이션 불필요).
  account_label(코드명·불변) / business_name(수동 사업자명) 은 보존.

기본값 없음 (NULL 허용) — username 미설정 계정 / 미로그인 페르소나 대응.
idempotent: ADD COLUMN IF NOT EXISTS.

주의: 단순 컬럼 추가만 수행한다. 인덱스식(인덱스 expression)은 추가하지 않는다.
  (과거 비-IMMUTABLE 인덱스식이 운영을 깨뜨린 사례가 있어 trivially safe 유지.)

Revision ID: 023
Revises: 022
Create Date: 2026-05-27
"""
from alembic import op


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_personas "
        "ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_personas DROP COLUMN IF EXISTS telegram_username"
    )
