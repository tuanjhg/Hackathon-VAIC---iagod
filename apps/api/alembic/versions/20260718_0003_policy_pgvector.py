"""Create the pgvector-backed policy retrieval schema.

Revision ID: 20260718_0003
Revises: 20260718_0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260718_0003_policy_rag"
down_revision: str | None = "20260718_0003_product_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS policy_rag")
    op.execute(
        """CREATE TABLE IF NOT EXISTS policy_rag.index_metadata (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
            dimension INTEGER NOT NULL,
            embedding_model TEXT NOT NULL
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS policy_rag.documents (
            source_path TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            title TEXT NOT NULL,
            indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS policy_rag.chunks (
            id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL REFERENCES policy_rag.documents(source_path) ON DELETE CASCADE,
            document_checksum TEXT NOT NULL,
            title TEXT NOT NULL,
            heading TEXT,
            content TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            embedding vector(384) NOT NULL,
            UNIQUE(source_path, chunk_index)
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS chunks_source_idx ON policy_rag.chunks(source_path)")
    op.execute(
        """CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
        ON policy_rag.chunks USING hnsw (embedding vector_cosine_ops)"""
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP SCHEMA IF EXISTS policy_rag CASCADE")
