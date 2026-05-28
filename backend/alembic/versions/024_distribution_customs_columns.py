"""distribution Priority 4 — 면장 컬럼 확장 (수출/수입 구분 + 추가 가격 항목).

배경:
- 21번 마이그레이션은 수입 면장만 가정해서 75% 역산이 declared_price 하나에만 걸렸다.
- 실제 첫 라이브 샘플은 수출신고필증이라 75% 역산이 의미 없는 13,112 같은 유령 수치를 만듦.
- 사용자가 검증할 근거(원본 단가/금액/한화 신고가격)도 화면에 없어 신뢰 흔들림.

변경:
- declaration_type TEXT: "export" / "import" (LLM 자동 인식). NULL 은 미지(legacy).
- item_name TEXT: ㉗ 품명 (예: "HAND BAG"). 기존 product 는 ㉚ 모델·규격(예: "GUCCI BAG") 유지.
- unit_price NUMERIC(15,2): ㉝ 단가 (USD 등). 검증용.
- declared_price_krw NUMERIC(15,2): ㊳ 신고가격 KRW 환산. 한화 직관성용.

역산 영향 (서비스 레벨에서 처리, 본 마이그레이션은 컬럼만):
- declaration_type='export' → actual_price = declared_price (75% 미적용).
- declaration_type='import' 또는 NULL → 기존 75% 역산 유지 (하위호환).

idempotent: ADD COLUMN IF NOT EXISTS.

Revision ID: 024
Revises: 023
Create Date: 2026-05-28
"""
from alembic import op


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE distribution_customs_declarations
            ADD COLUMN IF NOT EXISTS declaration_type TEXT,
            ADD COLUMN IF NOT EXISTS item_name TEXT,
            ADD COLUMN IF NOT EXISTS unit_price NUMERIC(15, 2),
            ADD COLUMN IF NOT EXISTS declared_price_krw NUMERIC(15, 2)
        """
    )

    # declaration_type 값 도메인 가드 — LLM 이 다른 값을 채우는 사고 방지.
    # NULL 허용(legacy 행 / 미지).
    op.execute(
        """
        ALTER TABLE distribution_customs_declarations
            DROP CONSTRAINT IF EXISTS ck_distribution_customs_declaration_type
        """
    )
    op.execute(
        """
        ALTER TABLE distribution_customs_declarations
            ADD CONSTRAINT ck_distribution_customs_declaration_type
            CHECK (declaration_type IS NULL OR declaration_type IN ('export', 'import'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE distribution_customs_declarations
            DROP CONSTRAINT IF EXISTS ck_distribution_customs_declaration_type
        """
    )
    op.execute(
        """
        ALTER TABLE distribution_customs_declarations
            DROP COLUMN IF EXISTS declared_price_krw,
            DROP COLUMN IF EXISTS unit_price,
            DROP COLUMN IF EXISTS item_name,
            DROP COLUMN IF EXISTS declaration_type
        """
    )
