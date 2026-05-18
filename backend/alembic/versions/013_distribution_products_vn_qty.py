"""distribution_products 에 VN 수량 3 컬럼 추가 (T9 명품재고대장 보강).

추가:
- vn_inventory_move_qty: VN재고 이동 수량 (Excel col 19, "VN재고 이동 수량")
- vn_sales_completed_qty: VN매출 완료 수량 (Excel col 21, "VN매출 완료 수량")
- vn_local_stock_qty: VN 현지 재고 수량 (Excel col 22, "VN 현지 재고 수량")

모두 nullable=True (과거 데이터 호환). 정수.

idempotent 보장:
- 컬럼이 이미 존재하면 add 를 skip (재실행 안전).
- downgrade 는 컬럼 존재 시에만 drop.

Revision ID: 013
Revises: 012
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 11+ 의 IF NOT EXISTS 사용. async bind 에서 sa.inspect() 가 작동 안 하는
    # 문제 회피. 컬럼이 이미 존재해도 ALTER 가 no-op 으로 통과.
    op.execute(
        "ALTER TABLE distribution_products "
        "ADD COLUMN IF NOT EXISTS vn_inventory_move_qty INTEGER"
    )
    op.execute(
        "ALTER TABLE distribution_products "
        "ADD COLUMN IF NOT EXISTS vn_sales_completed_qty INTEGER"
    )
    op.execute(
        "ALTER TABLE distribution_products "
        "ADD COLUMN IF NOT EXISTS vn_local_stock_qty INTEGER"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_products DROP COLUMN IF EXISTS vn_local_stock_qty"
    )
    op.execute(
        "ALTER TABLE distribution_products DROP COLUMN IF EXISTS vn_sales_completed_qty"
    )
    op.execute(
        "ALTER TABLE distribution_products DROP COLUMN IF EXISTS vn_inventory_move_qty"
    )
