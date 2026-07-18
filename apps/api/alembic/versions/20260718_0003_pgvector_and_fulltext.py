"""add pgvector embedding column + tsvector full-text search to products

Task 14 (INFRA): "bảng products (đa ngành, specs JSONB) + pgvector +
BM25/tsvector" per ADR B2 (docs/research/dmx-tech-decisions.md) and
docs/architecture.md "Mô hình dữ liệu" §kế hoạch mở rộng.

Postgres-only DDL (pgvector extension, HNSW/GIN indexes): guarded by a
dialect check so `alembic upgrade head` still runs clean against SQLite,
which the README documents as the supported local-dev-without-Docker path
(`DATABASE_URL` unset -> sqlite). Tests use `Base.metadata.create_all()`
directly (see tests/conftest.py) and never invoke Alembic, so this guard
only matters for that documented local-SQLite dev flow, not test isolation.

`unaccent`-folding for the tsvector column is deliberately deferred: the
built-in `unaccent()` function is STABLE (dictionary-lookup dependent), not
IMMUTABLE, so it cannot be used directly inside a `GENERATED ALWAYS AS`
expression without a custom IMMUTABLE wrapper function — left as follow-up
once the hybrid-retrieval code (ADR B2 adoption gate) actually needs it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260718_0003"
down_revision: str | None = "20260718_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# AITeamVN/Vietnamese_Embedding (ADR B3 primary choice) is a bge-m3-family
# model -> 1024 dims. Provisional: adjust if the embedding pipeline (later
# work) lands on a different model.
_EMBEDDING_DIM = 1024


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(f"ALTER TABLE products ADD COLUMN embedding vector({_EMBEDDING_DIM})")
    op.execute(
        "CREATE INDEX ix_products_embedding_hnsw ON products "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute(
        "ALTER TABLE products ADD COLUMN search_tsv tsvector "
        "GENERATED ALWAYS AS ("
        "  to_tsvector('simple', "
        "    coalesce(name, '') || ' ' || coalesce(brand, '') || ' ' || "
        "    coalesce(specs_raw::text, '')"
        "  )"
        ") STORED"
    )
    op.execute("CREATE INDEX ix_products_search_tsv ON products USING GIN (search_tsv)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_products_search_tsv")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS search_tsv")
    op.execute("DROP INDEX IF EXISTS ix_products_embedding_hnsw")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS embedding")
