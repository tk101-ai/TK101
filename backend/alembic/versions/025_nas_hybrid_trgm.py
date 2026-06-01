"""nas hybrid search — pg_trgm GIN index on chunk content

하이브리드 검색(의미검색 + 정확매칭)의 키워드 arm 용 인덱스.
- pg_trgm 트라이그램으로 content ILIKE '%term%' 를 색인 가속.
- 품번/금액/모델명/한글 부분일치를 언어 무관하게 매칭.
- 기존 임베딩/청크는 그대로 재사용 — 재인덱싱·backfill 불필요(인덱스가 기존 행을 커버).

Revision ID: 025
Revises: 024
Create Date: 2026-06-01
"""
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade():
    # pg_trgm extension 활성화. 이미 있으면 noop.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # content 트라이그램 GIN 인덱스 — ILIKE '%term%' 가속.
    # CONCURRENTLY는 트랜잭션 밖에서만 가능하므로 alembic 기본 트랜잭션과 충돌.
    # 1.2만 청크 규모는 일반 CREATE INDEX로 수 초 내 완료되므로 그대로 둔다.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_nas_text_chunks_content_trgm "
        "ON nas_text_chunks USING gin (content gin_trgm_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_nas_text_chunks_content_trgm")
    # pg_trgm extension은 다른 모듈이 쓸 수 있으므로 DROP하지 않음.
