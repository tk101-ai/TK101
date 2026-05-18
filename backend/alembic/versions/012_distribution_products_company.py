"""distribution_products 에 company_label 컬럼 추가 (T9 Phase F-A).

목적:
- 4개 회사 (TK101/래더엑스/뉴테인핏/SYBT) 데이터를 한 테이블에서 회사별로 분리.
- 회사별 wipe + insert 가능 → 다른 회사 데이터 보존.

기본값: NULL 허용. 기존 행은 UPDATE 로 "래더엑스" 채움 (현재 41MB 샘플 = 래더엑스 가정).

idempotent 보장:
- 컬럼/인덱스가 이미 존재하면 add/create 를 skip.
- backfill UPDATE 는 WHERE company_label IS NULL 조건으로 재실행 시 no-op.

Revision ID: 012
Revises: 011
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """alembic op 컨텍스트에서 컬럼 존재 여부 확인."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = [ix["name"] for ix in inspector.get_indexes(table)]
    return index_name in indexes


def upgrade() -> None:
    # 1) 컬럼 추가 (idempotent — 재실행 시 skip).
    if not _column_exists("distribution_products", "company_label"):
        op.add_column(
            "distribution_products",
            sa.Column("company_label", sa.String(100), nullable=True),
        )

    # 2) 기존 행 backfill — 현재 단일 회사 (래더엑스) 운영 가정.
    #    재실행 시 WHERE 조건으로 새로 NULL 인 행만 채움 (안전).
    op.execute(
        "UPDATE distribution_products "
        "SET company_label = '래더엑스' "
        "WHERE company_label IS NULL"
    )

    # 3) (company_label, brand) 복합 인덱스 — 회사별 조회 + 브랜드 필터 가속.
    if not _index_exists(
        "distribution_products", "ix_distribution_products_company_brand"
    ):
        op.create_index(
            "ix_distribution_products_company_brand",
            "distribution_products",
            ["company_label", "brand"],
        )


def downgrade() -> None:
    if _index_exists(
        "distribution_products", "ix_distribution_products_company_brand"
    ):
        op.drop_index(
            "ix_distribution_products_company_brand",
            table_name="distribution_products",
        )
    if _column_exists("distribution_products", "company_label"):
        op.drop_column("distribution_products", "company_label")
