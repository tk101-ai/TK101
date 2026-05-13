"""finance module enhancement — accounts/transactions 확장 + categories/counterparts/account_balance_snapshots 신규

목적:
- 재무 모듈 강화의 DB 기반 마련 (다른 모든 재무 작업의 선행 작업).
- accounts: 외화/대출/별칭/잔액 캐시 메타 추가.
- transactions: SHA256 hash 중복 방지, 카테고리/거래처 FK, soft delete, 태그/첨부.
- categories: 3단계 트리 (depth CHECK 제약), 자기 참조 FK.
- counterparts: 거래처 마스터, 별칭 ARRAY, 기본 카테고리.
- account_balance_snapshots: 잔액 시계열 (account_id, snapshot_date UNIQUE).
- upload_logs: 업로드 진단 메타 (bank_key, period_label, duplicate_count 등).

설계 메모:
- 모든 신규 컬럼은 nullable=True 또는 server_default 지정 → 무중단 마이그레이션.
- transaction_hash UNIQUE는 backfill 후 별도 마이그레이션에서 추가 (지금은 partial index만).
- categories.depth CHECK (<=3): 트리 깊이 폭주 방지. 애플리케이션에서도 재검증.
- ARRAY(String) 사용: tags, aliases 다중값 저장 (GIN 인덱스는 필요 시 추후).
- soft delete (is_deleted) + partial index 로 활성 거래 조회 최적화.

Revision ID: 007
Revises: 006
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # 1. categories (자기 참조 트리, 3단계 제한)
    # ---------------------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(50), nullable=True),
        # "#RRGGBB" 7자. UI 카테고리 색상 배지.
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column(
            "depth",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.CheckConstraint("depth <= 3", name="categories_depth_max_3"),
        sa.UniqueConstraint("code", name="uq_categories_code"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index("ix_categories_name", "categories", ["name"])

    # ---------------------------------------------------------------------
    # 2. counterparts (거래처 마스터)
    # ---------------------------------------------------------------------
    op.create_table(
        "counterparts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        # aliases: 거래처 별칭/이전 상호 등 다중값. GIN 인덱스는 추후.
        sa.Column("aliases", ARRAY(sa.String), nullable=True),
        sa.Column("business_registration_no", sa.String(20), nullable=True),
        sa.Column(
            "default_category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index("ix_counterparts_name", "counterparts", ["name"])
    op.create_index(
        "ix_counterparts_business_registration_no",
        "counterparts",
        ["business_registration_no"],
    )

    # ---------------------------------------------------------------------
    # 3. accounts 확장 (6개 컬럼 추가, 모두 무중단 가능)
    # ---------------------------------------------------------------------
    op.add_column(
        "accounts",
        sa.Column("account_type", sa.String(), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'KRW'"),
        ),
    )
    op.add_column(
        "accounts",
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column("account_label", sa.String(), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column("alias", sa.String(), nullable=True),
    )

    # ---------------------------------------------------------------------
    # 4. transactions 확장 (6개 컬럼 + 인덱스 4개)
    # ---------------------------------------------------------------------
    op.add_column(
        "transactions",
        sa.Column("transaction_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "counterpart_id",
            UUID(as_uuid=True),
            sa.ForeignKey("counterparts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("tags", ARRAY(sa.String), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("attachment_url", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "is_deleted",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # transactions 인덱스 5개: 기존 운영 테이블이므로 CONCURRENTLY로 트랜잭션 외부에서 생성.
    # CONCURRENTLY는 autocommit_block 필수 (트랜잭션 내부에서 사용 불가).
    with op.get_context().autocommit_block():
        # transaction_hash partial UNIQUE: NULL 다수 허용, 채워진 값만 (account_id, hash) 유일.
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_account_hash_unique "
            "ON transactions (account_id, transaction_hash) "
            "WHERE transaction_hash IS NOT NULL"
        )
        # 월별 집계용 — transaction_date 단독 인덱스.
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_transaction_date "
            "ON transactions (transaction_date)"
        )
        # category_id FK 인덱스.
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_category_id "
            "ON transactions (category_id)"
        )
        # counterpart_id FK 인덱스.
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_counterpart_id "
            "ON transactions (counterpart_id)"
        )
        # 활성 거래 조회 최적화 — soft delete 가 다수 누적되어도 인덱스 작게 유지.
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_is_deleted_false "
            "ON transactions (is_deleted) WHERE is_deleted = false"
        )

    # ---------------------------------------------------------------------
    # 5. account_balance_snapshots (잔액 시계열)
    # ---------------------------------------------------------------------
    op.create_table(
        "account_balance_snapshots",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("balance", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'KRW'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "account_id",
            "snapshot_date",
            name="uq_balance_snapshots_account_date",
        ),
    )
    op.create_index(
        "ix_balance_snapshots_snapshot_date",
        "account_balance_snapshots",
        ["snapshot_date"],
    )

    # ---------------------------------------------------------------------
    # 6. upload_logs 확장 (진단/통계 메타 4개)
    # ---------------------------------------------------------------------
    op.add_column(
        "upload_logs",
        sa.Column(
            "duplicate_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "upload_logs",
        sa.Column(
            "imported_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "upload_logs",
        sa.Column("bank_key", sa.String(20), nullable=True),
    )
    op.add_column(
        "upload_logs",
        sa.Column("period_label", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    # 역순 — 의존성: transactions → categories/counterparts/accounts.
    # 6. upload_logs 컬럼 4개 제거
    op.drop_column("upload_logs", "period_label")
    op.drop_column("upload_logs", "bank_key")
    op.drop_column("upload_logs", "imported_count")
    op.drop_column("upload_logs", "duplicate_count")

    # 5. account_balance_snapshots
    op.drop_index(
        "ix_balance_snapshots_snapshot_date",
        table_name="account_balance_snapshots",
    )
    op.drop_table("account_balance_snapshots")

    # 4. transactions 인덱스 + 컬럼 (FK도 함께 drop)
    # CONCURRENTLY로 생성한 인덱스는 CONCURRENTLY로 제거 (운영 테이블 락 회피).
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_is_deleted_false")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_counterpart_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_category_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_transaction_date")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_account_hash_unique")
    op.drop_column("transactions", "is_deleted")
    op.drop_column("transactions", "attachment_url")
    op.drop_column("transactions", "tags")
    # FK constraint는 drop_column에서 자동 처리 (PostgreSQL 의존성 cascade).
    op.drop_column("transactions", "counterpart_id")
    op.drop_column("transactions", "category_id")
    op.drop_column("transactions", "transaction_hash")

    # 3. accounts 컬럼 6개 제거
    op.drop_column("accounts", "alias")
    op.drop_column("accounts", "account_label")
    op.drop_column("accounts", "last_synced_at")
    op.drop_column("accounts", "current_balance")
    op.drop_column("accounts", "currency")
    op.drop_column("accounts", "account_type")

    # 2. counterparts
    op.drop_index(
        "ix_counterparts_business_registration_no", table_name="counterparts"
    )
    op.drop_index("ix_counterparts_name", table_name="counterparts")
    op.drop_table("counterparts")

    # 1. categories
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_table("categories")
