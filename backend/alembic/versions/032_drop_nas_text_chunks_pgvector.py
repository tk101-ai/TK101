"""drop legacy nas_text_chunks + pgvector extension

검색 코퍼스가 Qdrant(Qwen3 2560-dim) 단일 소스로 이관된 뒤, 레거시 pgvector 청크
테이블(nas_text_chunks, e5 1024-dim)은 검색에 전혀 반영되지 않는 dead data였다.
인앱 인덱싱/backfill 경로도 이미 410으로 비활성. 테이블과 pgvector 확장을 제거한다.

nas_files(파일 메타)는 목록/다운로드/상태에 계속 쓰이므로 유지한다.

Revision ID: 032
Revises: 031
"""
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 자식 테이블만 제거(FK·trgm 인덱스는 CASCADE로 함께 정리). nas_files는 유지.
    op.execute("DROP TABLE IF EXISTS nas_text_chunks CASCADE")
    # vector 타입을 쓰는 컬럼이 더는 없으므로 확장 제거 가능.
    op.execute("DROP EXTENSION IF EXISTS vector")


def downgrade() -> None:
    # 레거시 스키마 재생성(데이터는 복구 불가 — 외부 Qdrant 파이프라인이 소스).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE nas_text_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            file_id UUID NOT NULL REFERENCES nas_files(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1024) NOT NULL,
            token_count INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_nas_text_chunks_file_id", "nas_text_chunks", ["file_id"]
    )
