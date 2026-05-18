"""distribution Phase B-1 — 주차별 종합 데이터 + 명품재고대장 테이블 추가.

목적 (T9 Phase B 요구사항.txt):
- distribution_weekly_summary: 주차별 매입/이동/매출 + 입금요청 매트릭스
  (종합관리시트 1주차 = 1행). 회사·기간 unique.
- distribution_products: 명품재고대장 (브랜드/제품명/카테고리/재고).
  business 카테고리는 매입 대화 시 "이 제품들 더 확보" 자동 멘션에 사용.

설계 메모:
- weekly_summary 의 raw_row 에 원본 엑셀 행 보존 → 양식 변경에도 재처리 가능.
- products 는 매주 풀 갱신 (UPSERT) — 변동 이력 추적은 v0.3 별도.
- 한국 4 페르소나 1:1 페어 구조에 맞춰 source/target 페르소나 관계 결정은 라우터 단에서.

Revision ID: 011
Revises: 010
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # distribution_weekly_summary — 주차별 종합 데이터 (래더엑스 종합관리시트)
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_weekly_summary",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # company_label: "래더엑스" 등. 다회사 확장 대비.
        sa.Column("company_label", sa.String(100), nullable=False),
        # period_label: "1201_1207" 원본 표기 — 표시·디버깅용.
        sa.Column("period_label", sa.String(30), nullable=False),
        # period_start/end: ISO 날짜로 정규화. 회계 연도 추론.
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        # 사람 기입 (white background in Excel)
        sa.Column("kr_purchase", sa.Numeric(15, 2), nullable=True),
        sa.Column("vn_inventory_move", sa.Numeric(15, 2), nullable=True),
        sa.Column("vn_sales_completed", sa.Numeric(15, 2), nullable=True),
        # 자동 계산 (blue background): KR=40%, VN재고=30%, VN매출=30%
        sa.Column("kr_purchase_deposit_req", sa.Numeric(15, 2), nullable=True),
        sa.Column("vn_inventory_deposit_req", sa.Numeric(15, 2), nullable=True),
        sa.Column("vn_sales_deposit_req", sa.Numeric(15, 2), nullable=True),
        # 입금 결과 (사람 기입)
        sa.Column("account_deposit", sa.Numeric(15, 2), nullable=True),
        sa.Column("cash_deposit", sa.Numeric(15, 2), nullable=True),
        # 원본 보존
        sa.Column("raw_row", JSONB, nullable=True),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "imported_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # 동일 회사·기간 중복 적재 방지. UPSERT 시 동일 row 갱신.
        sa.UniqueConstraint(
            "company_label",
            "period_start",
            "period_end",
            name="uq_distribution_weekly_summary_period",
        ),
    )
    op.create_index(
        "ix_distribution_weekly_summary_company_start",
        "distribution_weekly_summary",
        ["company_label", sa.text("period_start DESC")],
    )

    # ---------------------------------------------------------------------
    # distribution_products — 명품재고대장
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_products",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # 브랜드명: 정규화하지 않고 원본 그대로 (고야드 vs GOYARD 등 표기 변동 보존).
        sa.Column("brand", sa.String(100), nullable=False),
        sa.Column("product_name_en", sa.String(500), nullable=True),
        # product_code: 동일 브랜드 내 unique 가정. UPSERT key.
        sa.Column("product_code", sa.String(100), nullable=True),
        # 카테고리: Bag / Belts / Ring / Scarf 등. 자동 분류 후보.
        sa.Column("category", sa.String(50), nullable=True),
        # 수량
        sa.Column("purchase_qty", sa.Integer, nullable=True),
        sa.Column("domestic_stock_qty", sa.Integer, nullable=True),
        # 가격 (KRW)
        sa.Column("supply_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("vat", sa.Numeric(15, 2), nullable=True),
        sa.Column("purchase_price", sa.Numeric(15, 2), nullable=True),
        # 매입 메타
        sa.Column("approval_number", sa.String(50), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=True),
        # 원본 보존
        sa.Column("raw_row", JSONB, nullable=True),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "imported_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_distribution_products_brand",
        "distribution_products",
        ["brand", "category"],
    )

    # ---------------------------------------------------------------------
    # distribution_personas — business_name 컬럼 추가 (사업자명 라벨)
    # ---------------------------------------------------------------------
    # 기존 account_label 은 코드명 (KR-A1) 으로 라우팅·세션 파일명 용도 유지.
    # business_name 은 UI 표시용 사업자명 (예: "주식회사 XYZ"). NULL 이면 display_name 폴백.
    op.add_column(
        "distribution_personas",
        sa.Column("business_name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("distribution_personas", "business_name")
    op.drop_index(
        "ix_distribution_products_brand",
        table_name="distribution_products",
    )
    op.drop_table("distribution_products")
    op.drop_index(
        "ix_distribution_weekly_summary_company_start",
        table_name="distribution_weekly_summary",
    )
    op.drop_table("distribution_weekly_summary")
