import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

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
            if force_reset:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {schema}.index_metadata (
                    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                    dimension INTEGER NOT NULL,
                    embedding_model TEXT NOT NULL
                )"""
            )
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {schema}.documents (
                    source_path TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    title TEXT NOT NULL,
                    indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {schema}.chunks (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL REFERENCES {schema}.documents(source_path)
                        ON DELETE CASCADE,
                    document_checksum TEXT NOT NULL,
                    title TEXT NOT NULL,
                    heading TEXT,
                    content TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    embedding vector({self.dimension}) NOT NULL,
                    UNIQUE(source_path, chunk_index)
                )"""
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS chunks_source_idx ON {schema}.chunks(source_path)"
            )
            cursor.execute(
                f"""CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
                ON {schema}.chunks USING hnsw (embedding vector_cosine_ops)"""
            )
            cursor.execute(
                """SELECT format_type(attribute.atttypid, attribute.atttypmod) AS vector_type
                FROM pg_attribute AS attribute
                JOIN pg_class AS relation ON relation.oid = attribute.attrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = %s AND relation.relname = 'chunks'
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
            cursor.execute(f"SELECT source_path, checksum FROM {self.schema}.documents")
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
            cursor.execute(f"DELETE FROM {schema}.documents WHERE source_path = %s", (source_path,))
            cursor.execute(
                f"""INSERT INTO {schema}.documents(source_path, checksum, title)
                VALUES (%s, %s, %s)""",
                (source_path, checksum, title),
            )
            rows = [
                (
                    chunk.id,
                    chunk.source_path,
                    chunk.document_checksum,
                    chunk.title,
                    chunk.heading,
                    chunk.content,
                    chunk.chunk_index,
                    chunk.line_start,
                    chunk.line_end,
                    vector_literal(embedding, self.dimension),
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
            cursor.executemany(
                f"""INSERT INTO {schema}.chunks
                (id, source_path, document_checksum, title, heading, content, chunk_index,
                 line_start, line_end, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)""",
                rows,
            )

    def remove_documents_except(self, source_paths: set[str]) -> int:
        removed = set(self.checksums()) - source_paths
        if removed:
            with self._connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {self.schema}.documents WHERE source_path = ANY(%s)",
                    (list(removed),),
                )
        return len(removed)

    def search(self, query_embedding: Sequence[float], limit: int = 5) -> list[SearchResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        vector = vector_literal(query_embedding, self.dimension)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT id, source_path, document_checksum, title, heading, content,
                    chunk_index, line_start, line_end,
                    1 - (embedding <=> %s::vector) AS score
                FROM {self.schema}.chunks
                ORDER BY embedding <=> %s::vector, id
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
            cursor.execute(f"SELECT COUNT(*) AS count FROM {self.schema}.documents")
            document_row = cursor.fetchone()
            if document_row is None:
                raise RuntimeError("Unable to read document count")
            documents = int(document_row["count"])
            cursor.execute(f"SELECT COUNT(*) AS count FROM {self.schema}.chunks")
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
