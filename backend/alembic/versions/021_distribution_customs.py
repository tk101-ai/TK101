"""distribution Priority 4 — 면장(통관신고) 데이터 적재 테이블 추가.

목적 (Priority 4 — 면장/customs declaration data collection):
- distribution_customs_declarations: 면장(customs declaration) 1행.
  신고번호(declaration_number) / 신고가(declared_price) / 재고(stock_qty) 수집.

핵심 비즈니스 규칙:
- 면장의 신고가는 관세 절감 목적으로 실제 가치의 75% 로 신고된다.
- 실가 역산: actual_price = declared_price / 0.75 (비율은 config 조정 가능).
- 역산값은 파서가 적재 시점에 계산해 actual_price 컬럼에 저장.

설계 메모:
- declaration_number partial UNIQUE: 채워진 값만 유일 (NULL 다수 허용).
  social_posts 의 external_id partial unique index 와 동일 패턴.
- raw_row(JSONB, NOT NULL): 원본 엑셀 행 보존 → 컬럼 매핑 변경에도 재처리 가능.
- 회사/신고번호/신고일자 조회 최적화용 보조 인덱스.

idempotent: CREATE TABLE / INDEX IF NOT EXISTS (최근 마이그레이션 스타일과 일치).

Revision ID: 021
Revises: 020
Create Date: 2026-05-27
"""
from alembic import op


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # distribution_customs_declarations — 면장(통관신고) 적재
    # ---------------------------------------------------------------------
    # gen_random_uuid() / TIMESTAMPTZ / JSONB 는 다른 distribution 테이블과 동일 규약.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS distribution_customs_declarations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_label TEXT,
            bl_number TEXT,
            declaration_number TEXT,
            product TEXT,
            declared_price NUMERIC(15, 2),
            actual_price NUMERIC(15, 2),
            currency TEXT,
            stock_qty INTEGER,
            declared_at DATE,
            raw_row JSONB NOT NULL,
            source_file TEXT,
            imported_by UUID REFERENCES users(id) ON DELETE SET NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # 신고번호 partial UNIQUE — 채워진 값만 유일, NULL 다수 허용.
    # (social_posts.external_id partial unique index 와 동일 전략.)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_distribution_customs_declaration_number "
        "ON distribution_customs_declarations (declaration_number) "
        "WHERE declaration_number IS NOT NULL"
    )

    # 회사 + 신고일자 조회/정렬 최적화.
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_distribution_customs_company_declared_at "
        "ON distribution_customs_declarations (company_label, declared_at DESC)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_distribution_customs_company_declared_at"
    )
    op.execute(
        "DROP INDEX IF EXISTS uq_distribution_customs_declaration_number"
    )
    op.execute("DROP TABLE IF EXISTS distribution_customs_declarations")
