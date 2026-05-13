"""finance module fixes — partial unique index + currency server_default 정합성

목적 (코드리뷰 CRITICAL-3 + HIGH-6):
- ix_transactions_account_hash_unique: WHERE 절에 is_deleted=false 추가.
  soft delete 된 거래는 unique set 에서 제외해야 활성 중복만 차단된다.
- accounts.currency / account_balance_snapshots.currency:
  server_default 를 raw "KRW" → text("'KRW'") 형태로 일관화.
  (모델측 변경은 코드에서 처리; 마이그레이션은 idempotent 하게 재선언)

Revision ID: 008
Revises: 007
Create Date: 2026-05-12
"""
from alembic import op


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 기존 partial unique index 재작성 (is_deleted=false 조건 추가)
    # transactions 는 운영 테이블이므로 CONCURRENTLY + autocommit_block 필수.
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_account_hash_unique")
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_account_hash_unique "
            "ON transactions (account_id, transaction_hash) "
            "WHERE transaction_hash IS NOT NULL AND is_deleted = false"
        )

    # 2. server_default 정합성 (PG 레벨에서는 동일하지만 모델/alembic diff 노이즈 차단)
    op.execute("ALTER TABLE accounts ALTER COLUMN currency SET DEFAULT 'KRW'")
    op.execute(
        "ALTER TABLE account_balance_snapshots ALTER COLUMN currency SET DEFAULT 'KRW'"
    )


def downgrade() -> None:
    # partial unique index 를 007 형태로 되돌림 (is_deleted 조건 제거)
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_account_hash_unique")
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_account_hash_unique "
            "ON transactions (account_id, transaction_hash) "
            "WHERE transaction_hash IS NOT NULL"
        )
    # currency default 는 그대로 둠 (동일 값이라 의미 없음)
