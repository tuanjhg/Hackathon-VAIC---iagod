import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.rag.models import PolicyChunk, SearchResult

_SAFE_SCHEMA = re.compile(r"^[a-z_][a-z0-9_]*$")


def normalize_psycopg_url(database_url: str) -> str:
    """Convert a SQLAlchemy psycopg URL into a libpq-compatible URL."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def vector_literal(vector: Sequence[float], dimension: int) -> str:
    if len(vector) != dimension:
        raise ValueError(f"Expected embedding dimension {dimension}, got {len(vector)}")
    return "[" + ",".join(format(float(value), ".9g") for value in vector) + "]"


class PgVectorStore:
    """PostgreSQL pgvector store using server-side cosine nearest-neighbor search."""

    def __init__(
        self,
        database_url: str,
        dimension: int,
        embedding_model: str,
        schema: str = "policy_rag",
        force_reset: bool = False,
    ) -> None:
        if not _SAFE_SCHEMA.fullmatch(schema):
            raise ValueError("schema must be a lowercase PostgreSQL identifier")
        if dimension < 32 or dimension > 2000:
            raise ValueError("pgvector HNSW dimension must be between 32 and 2000")
        self.database_url = normalize_psycopg_url(database_url)
        self.dimension = dimension
        self.embedding_model = embedding_model
        self.schema = schema
        self._initialize(force_reset)

    @contextmanager
    def _connection(self) -> Iterator[Connection[dict[str, Any]]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def _initialize(self, force_reset: bool) -> None:
        schema = self.schema
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            if force_reset:
                cursor.execute(f"DROP TABLE IF EXISTS {schema}.policy_chunks")
                cursor.execute(f"DROP TABLE IF EXISTS {schema}.policy_documents")
                cursor.execute(f"DROP TABLE IF EXISTS {schema}.index_metadata")
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {schema}.index_metadata (
                    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                    dimension INTEGER NOT NULL,
                    embedding_model TEXT NOT NULL
                )"""
            )
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {schema}.policy_documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_path TEXT NOT NULL UNIQUE,
                    title TEXT,
                    checksum VARCHAR(128) NOT NULL UNIQUE,
                    document_type VARCHAR(100),
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {schema}.policy_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES {schema}.policy_documents(id)
                        ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding vector({self.dimension}),
                    embedding_model VARCHAR(150),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(document_id, chunk_index)
                )"""
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_policy_chunks_document_id "
                f"ON {schema}.policy_chunks(document_id)"
            )
            cursor.execute(
                f"""CREATE INDEX IF NOT EXISTS idx_policy_chunks_embedding_hnsw
                ON {schema}.policy_chunks USING hnsw (embedding vector_cosine_ops)"""
            )
            cursor.execute(
                """SELECT format_type(attribute.atttypid, attribute.atttypmod) AS vector_type
                FROM pg_attribute AS attribute
                JOIN pg_class AS relation ON relation.oid = attribute.attrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = %s AND relation.relname = 'policy_chunks'
                  AND attribute.attname = 'embedding'""",
                (schema,),
            )
            vector_type = cursor.fetchone()
            if vector_type and vector_type["vector_type"] != f"vector({self.dimension})":
                raise ValueError(
                    "Vector database dimension does not match; rebuild with --force"
                )
            cursor.execute(
                f"SELECT dimension, embedding_model FROM {schema}.index_metadata WHERE singleton"
            )
            metadata = cursor.fetchone()
            if metadata and (
                metadata["dimension"] != self.dimension
                or metadata["embedding_model"] != self.embedding_model
            ):
                raise ValueError(
                    "Vector database embedding configuration does not match; rebuild with --force"
                )
            cursor.execute(
                f"""INSERT INTO {schema}.index_metadata(singleton, dimension, embedding_model)
                VALUES (TRUE, %s, %s) ON CONFLICT (singleton) DO NOTHING""",
                (self.dimension, self.embedding_model),
            )

    def checksums(self) -> dict[str, str]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT source_path, checksum FROM {self.schema}.policy_documents")
            return {str(row["source_path"]): str(row["checksum"]) for row in cursor.fetchall()}

    def replace_document(
        self,
        source_path: str,
        title: str,
        checksum: str,
        chunks: Sequence[PolicyChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        schema = self.schema
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {schema}.policy_documents WHERE source_path = %s", (source_path,)
            )
            cursor.execute(
                f"""INSERT INTO {schema}.policy_documents(
                    source_path, checksum, title, document_type)
                VALUES (%s, %s, %s, 'markdown') RETURNING id""",
                (source_path, checksum, title),
            )
            document = cursor.fetchone()
            if document is None:
                raise RuntimeError("Unable to create policy document")
            rows = [
                (
                    document["id"],
                    chunk.chunk_index,
                    chunk.content,
                    len(chunk.content.split()),
                    Jsonb({
                        "legacy_id": chunk.id,
                        "source_path": chunk.source_path,
                        "document_checksum": chunk.document_checksum,
                        "title": chunk.title,
                        "heading": chunk.heading,
                        "line_start": chunk.line_start,
                        "line_end": chunk.line_end,
                    }),
                    vector_literal(embedding, self.dimension),
                    self.embedding_model,
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
            cursor.executemany(
                f"""INSERT INTO {schema}.policy_chunks
                (document_id, chunk_index, content, token_count, metadata, embedding, embedding_model)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector, %s)""",
                rows,
            )

    def remove_documents_except(self, source_paths: set[str]) -> int:
        removed = set(self.checksums()) - source_paths
        if removed:
            with self._connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {self.schema}.policy_documents WHERE source_path = ANY(%s)",
                    (list(removed),),
                )
        return len(removed)

    def search(self, query_embedding: Sequence[float], limit: int = 5) -> list[SearchResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        vector = vector_literal(query_embedding, self.dimension)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT c.id, d.source_path, d.checksum AS document_checksum,
                    d.title, c.metadata->>'heading' AS heading, c.content,
                    c.chunk_index,
                    COALESCE((c.metadata->>'line_start')::integer, 0) AS line_start,
                    COALESCE((c.metadata->>'line_end')::integer, 0) AS line_end,
                    1 - (c.embedding <=> %s::vector) AS score
                FROM {self.schema}.policy_chunks c
                JOIN {self.schema}.policy_documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector, c.id
                LIMIT %s""",
                (vector, vector, limit),
            )
            return [
                SearchResult(
                    chunk=PolicyChunk(
                        id=str(row["id"]),
                        source_path=str(row["source_path"]),
                        document_checksum=str(row["document_checksum"]),
                        title=str(row["title"]),
                        heading=None if row["heading"] is None else str(row["heading"]),
                        content=str(row["content"]),
                        chunk_index=int(row["chunk_index"]),
                        line_start=int(row["line_start"]),
                        line_end=int(row["line_end"]),
                    ),
                    score=float(row["score"]),
                )
                for row in cursor.fetchall()
            ]

    def stats(self) -> dict[str, int | str]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {self.schema}.policy_documents")
            document_row = cursor.fetchone()
            if document_row is None:
                raise RuntimeError("Unable to read document count")
            documents = int(document_row["count"])
            cursor.execute(f"SELECT COUNT(*) AS count FROM {self.schema}.policy_chunks")
            chunk_row = cursor.fetchone()
            if chunk_row is None:
                raise RuntimeError("Unable to read chunk count")
            chunks = int(chunk_row["count"])
        return {
            "documents": documents,
            "chunks": chunks,
            "dimension": self.dimension,
            "embedding_model": self.embedding_model,
            "backend": "postgresql+pgvector",
        }
