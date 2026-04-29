"""nas search tables (files + text chunks with pgvector)

Revision ID: 004
Revises: 003
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    # 1. pgvector extension 활성화. 이미 있으면 noop.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. nas_files: NAS 상의 파일 1개 = 1 row.
    op.create_table(
        "nas_files",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("path", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("mime_type", sa.Text, nullable=True),
        sa.Column(
            "file_type",
            sa.Text,
            nullable=False,
            server_default=sa.text("'document'"),
        ),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("mtime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_hash", sa.Text, nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "file_type IN ('document','image')",
            name="nas_files_file_type_check",
        ),
    )
    op.create_index("ix_nas_files_path", "nas_files", ["path"])
    op.create_index("ix_nas_files_mtime", "nas_files", ["mtime"])

    # 3. nas_text_chunks: pgvector 컬럼은 raw SQL로 생성해 alembic 호환성 보장.
    op.execute(
        """
        CREATE TABLE nas_text_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            file_id uuid NOT NULL REFERENCES nas_files(id) ON DELETE CASCADE,
            chunk_index integer NOT NULL,
            content text NOT NULL,
            embedding vector(1024) NOT NULL,
            token_count integer,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz
        )
        """
    )

    op.create_index(
        "ix_nas_text_chunks_file_id",
        "nas_text_chunks",
        ["file_id"],
    )
    # ivfflat + cosine. lists=100은 일반적인 시작값(데이터 늘면 재튜닝).
    op.execute(
        "CREATE INDEX ix_nas_text_chunks_embedding "
        "ON nas_text_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_nas_text_chunks_embedding")
    op.drop_index("ix_nas_text_chunks_file_id", table_name="nas_text_chunks")
    op.execute("DROP TABLE IF EXISTS nas_text_chunks")
    op.drop_index("ix_nas_files_mtime", table_name="nas_files")
    op.drop_index("ix_nas_files_path", table_name="nas_files")
    op.drop_table("nas_files")
    # pgvector extension은 다른 모듈에서 사용할 수 있으므로 DROP하지 않음.
