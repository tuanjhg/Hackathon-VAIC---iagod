"""Build the hybrid relational + JSONB + typed-facet catalog.

Revision ID: 20260718_0005
Revises: 20260718_0004

The upgrade is deliberately additive: legacy price, promotion, inventory and
raw category tables are retained until production verification is complete.
Downgrade removes data written only to the new tables and therefore must be
preceded by a backup. BIGINT widening is intentionally not reversed because a
future value may no longer fit INTEGER safely.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "20260718_0005"
down_revision: str | None = "20260718_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CATEGORY_CODES = {
    "tu-lanh": "refrigerators",
    "may-lanh": "air_conditioners",
    "may-giat": "washing_machines",
    "may-say-quan-ao": "clothes_dryers",
    "may-rua-chen": "dishwashers",
    "tu-mat-tu-dong": "coolers_freezers",
    "may-nuoc-nong": "water_heaters",
    "micro-karaoke": "karaoke_microphones",
    "micro-thu-am-dien-thoai": "phone_recording_microphones",
    "dong-ho-thong-minh": "smartwatches",
    "may-tinh-de-ban": "desktop_computers",
    "man-hinh-may-tinh": "computer_monitors",
    "may-in": "printers",
    "may-tinh-bang": "tablets",
}


def _embedding_dimension() -> int:
    value = int(os.getenv("POLICY_EMBEDDING_DIMENSION", "384"))
    if not 32 <= value <= 2000:
        raise ValueError("POLICY_EMBEDDING_DIMENSION must be between 32 and 2000")
    return value


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Hybrid catalog migration requires PostgreSQL")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Widen identifiers before introducing the new BIGINT foreign keys.
    for table, constraint in (
        ("products", "products_category_id_fkey"),
        ("product_specs", "product_specs_product_id_fkey"),
        ("prices", "prices_product_id_fkey"),
        ("inventory", "inventory_product_id_fkey"),
        ("promotions", "promotions_product_id_fkey"),
    ):
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    op.execute("ALTER TABLE categories ALTER COLUMN id TYPE BIGINT")
    op.execute("ALTER TABLE products ALTER COLUMN id TYPE BIGINT")
    op.execute("ALTER TABLE products ALTER COLUMN category_id TYPE BIGINT")
    for table in ("product_specs", "prices", "inventory", "promotions"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN product_id TYPE BIGINT")
    for sequence in (
        "categories_id_seq",
        "products_id_seq",
        "product_specs_id_seq",
        "prices_id_seq",
        "inventory_id_seq",
        "promotions_id_seq",
    ):
        op.execute(f"ALTER SEQUENCE IF EXISTS {sequence} AS BIGINT")
    op.execute(
        "ALTER TABLE products ADD CONSTRAINT products_category_id_fkey "
        "FOREIGN KEY (category_id) REFERENCES categories(id)"
    )
    op.execute(
        "ALTER TABLE product_specs ADD CONSTRAINT product_specs_product_id_fkey "
        "FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE"
    )
    for table in ("prices", "inventory", "promotions"):
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_product_id_fkey "
            "FOREIGN KEY (product_id) REFERENCES products(id)"
        )

    op.execute("ALTER TABLE categories ADD COLUMN code VARCHAR(100)")
    op.execute("ALTER TABLE categories ADD COLUMN description TEXT")
    op.execute("ALTER TABLE categories ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE categories ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    op.execute("ALTER TABLE categories ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    op.execute("ALTER TABLE categories ALTER COLUMN name TYPE VARCHAR(255)")
    op.execute("ALTER TABLE categories ALTER COLUMN slug TYPE VARCHAR(150)")
    case_sql = " ".join(
        f"WHEN '{slug}' THEN '{code}'" for slug, code in CATEGORY_CODES.items()
    )
    op.execute(f"UPDATE categories SET code = CASE slug {case_sql} ELSE slug END")
    op.execute("ALTER TABLE categories ALTER COLUMN code SET NOT NULL")
    op.execute("ALTER TABLE categories ADD CONSTRAINT categories_code_key UNIQUE (code)")

    op.execute(
        """CREATE TABLE brands (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            normalized_name VARCHAR(150) NOT NULL UNIQUE,
            source_brand_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        """WITH normalized AS (
            SELECT DISTINCT ON (normalized_name)
                brand AS name,
                normalized_name
            FROM (
                SELECT brand,
                    regexp_replace(
                        regexp_replace(lower(btrim(brand)),
                            '\\s+(việt nam|viet nam|vietnam)$', '', 'i'),
                        '\\s+', ' ', 'g'
                    ) AS normalized_name
                FROM products
                WHERE brand IS NOT NULL AND btrim(brand) <> ''
            ) source
            ORDER BY normalized_name, name
        )
        INSERT INTO brands(name, normalized_name)
        SELECT name, normalized_name FROM normalized
        ON CONFLICT (normalized_name) DO NOTHING"""
    )

    op.execute("ALTER TABLE products ALTER COLUMN sku TYPE VARCHAR(100)")
    op.execute("ALTER TABLE products ADD COLUMN product_web_id VARCHAR(100)")
    op.execute("ALTER TABLE products ADD COLUMN model_code VARCHAR(150)")
    op.execute("ALTER TABLE products ADD COLUMN brand_id BIGINT REFERENCES brands(id)")
    op.execute("ALTER TABLE products ADD COLUMN display_name VARCHAR(500)")
    op.execute("ALTER TABLE products ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'active'")
    op.execute("ALTER TABLE products ADD COLUMN source_data JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        """WITH web_id_counts AS (
            SELECT product_web_id, count(*) AS occurrences
            FROM catalog_products
            WHERE product_web_id IS NOT NULL AND btrim(product_web_id) <> ''
            GROUP BY product_web_id
        )
        UPDATE products p SET
            product_web_id = CASE WHEN wc.occurrences = 1 THEN cp.product_web_id END,
            model_code = cp.model_code,
            display_name = p.name,
            source_data = jsonb_build_object(
                'source_category', cp.source_category,
                'source_file', cp.source_file,
                'source_hash', cp.source_hash,
                'raw_product_web_id', cp.product_web_id
            )
        FROM catalog_products cp
        LEFT JOIN web_id_counts wc ON wc.product_web_id = cp.product_web_id
        WHERE cp.sku = p.sku"""
    )
    op.execute(
        """UPDATE products p SET brand_id = b.id
        FROM brands b
        WHERE b.normalized_name = regexp_replace(
            regexp_replace(lower(btrim(p.brand)),
                '\\s+(việt nam|viet nam|vietnam)$', '', 'i'),
            '\\s+', ' ', 'g')"""
    )
    op.execute("ALTER TABLE products ALTER COLUMN display_name SET NOT NULL")
    op.execute(
        "ALTER TABLE products ADD CONSTRAINT products_status_check "
        "CHECK (status IN ('active', 'inactive', 'draft', 'archived'))"
    )
    op.execute("CREATE UNIQUE INDEX products_product_web_id_key ON products(product_web_id) WHERE product_web_id IS NOT NULL")
    op.execute("CREATE INDEX idx_products_category_id ON products(category_id)")
    op.execute("CREATE INDEX idx_products_brand_id ON products(brand_id)")
    op.execute("CREATE INDEX idx_products_model_code ON products(model_code)")
    op.execute("CREATE INDEX idx_products_status ON products(status)")
    op.execute("CREATE INDEX idx_products_category_brand ON products(category_id, brand_id)")

    op.execute("ALTER TABLE product_specs ADD COLUMN raw_specs JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE product_specs ADD COLUMN normalized_specs JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE product_specs ADD COLUMN search_text TEXT")
    op.execute("ALTER TABLE product_specs ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    op.execute("ALTER TABLE product_specs ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    op.execute(
        """UPDATE product_specs ps SET
            raw_specs = p.specifications,
            search_text = concat_ws(' ', p.name, p.brand, p.short_description,
                p.specifications::text)
        FROM products p WHERE p.id = ps.product_id"""
    )
    op.execute("ALTER TABLE product_specs DROP CONSTRAINT product_specs_pkey")
    op.execute("ALTER TABLE product_specs DROP CONSTRAINT product_specs_product_id_key")
    op.execute("ALTER TABLE product_specs ADD CONSTRAINT product_specs_legacy_id_key UNIQUE (id)")
    op.execute("ALTER TABLE product_specs ADD CONSTRAINT product_specs_pkey PRIMARY KEY (product_id)")
    op.execute("CREATE INDEX idx_product_specs_raw_gin ON product_specs USING GIN (raw_specs)")
    op.execute(
        "CREATE INDEX idx_product_specs_normalized_gin ON product_specs "
        "USING GIN (normalized_specs jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX idx_product_specs_search_text ON product_specs "
        "USING GIN (to_tsvector('simple', coalesce(search_text, '')))"
    )

    op.execute(
        """CREATE TABLE import_batches (
            id BIGSERIAL PRIMARY KEY,
            source_file VARCHAR(500) NOT NULL,
            category_code VARCHAR(100) NOT NULL,
            checksum VARCHAR(128),
            status VARCHAR(30) NOT NULL,
            total_rows INTEGER NOT NULL DEFAULT 0,
            success_rows INTEGER NOT NULL DEFAULT 0,
            failed_rows INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT import_batches_status_check CHECK (
                status IN ('pending','processing','completed','completed_with_errors','failed')
            )
        )"""
    )
    op.execute("CREATE INDEX idx_import_batches_category_code ON import_batches(category_code)")
    op.execute(
        """CREATE TABLE raw_product_rows (
            id BIGSERIAL PRIMARY KEY,
            batch_id BIGINT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            raw_data JSONB NOT NULL,
            import_status VARCHAR(30) NOT NULL DEFAULT 'pending',
            product_id BIGINT REFERENCES products(id),
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT raw_product_rows_batch_row_key UNIQUE(batch_id, row_number),
            CONSTRAINT raw_product_rows_status_check CHECK (
                import_status IN ('pending','processing','imported','skipped','failed')
            )
        )"""
    )
    op.execute("CREATE INDEX idx_raw_product_rows_product_id ON raw_product_rows(product_id)")

    op.execute(
        """CREATE TABLE product_offers (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            original_price NUMERIC(15,2),
            sale_price NUMERIC(15,2),
            currency CHAR(3) NOT NULL DEFAULT 'VND',
            gifts JSONB NOT NULL DEFAULT '[]'::jsonb,
            valid_from TIMESTAMPTZ,
            valid_to TIMESTAMPTZ,
            is_current BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT product_offers_original_price_check CHECK (
                original_price IS NULL OR original_price >= 0),
            CONSTRAINT product_offers_sale_price_check CHECK (
                sale_price IS NULL OR sale_price >= 0),
            CONSTRAINT product_offers_price_order_check CHECK (
                original_price IS NULL OR sale_price IS NULL OR sale_price <= original_price),
            CONSTRAINT product_offers_validity_check CHECK (
                valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
            CONSTRAINT product_offers_gifts_array_check CHECK (jsonb_typeof(gifts) = 'array')
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_one_current_offer_per_product ON product_offers(product_id) "
        "WHERE is_current = TRUE"
    )
    op.execute("CREATE INDEX idx_product_offers_product_id ON product_offers(product_id)")
    op.execute("CREATE INDEX idx_product_offers_sale_price ON product_offers(sale_price) WHERE is_current")
    op.execute(
        """INSERT INTO product_offers(
            product_id, original_price, sale_price, currency, gifts, valid_from, valid_to
        )
        SELECT pr.product_id, pr.original_price, pr.sale_price, pr.currency::CHAR(3),
            CASE WHEN pm.description IS NULL OR btrim(pm.description) = '' THEN '[]'::jsonb
                 ELSE jsonb_build_array(jsonb_build_object(
                    'type', 'gift', 'name', pm.description)) END,
            pm.valid_from, pm.valid_to
        FROM prices pr LEFT JOIN promotions pm ON pm.product_id = pr.product_id"""
    )

    op.execute(
        """CREATE TABLE attribute_definitions (
            id BIGSERIAL PRIMARY KEY,
            category_id BIGINT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            attribute_key VARCHAR(150) NOT NULL,
            source_column VARCHAR(150),
            display_name VARCHAR(255) NOT NULL,
            data_type VARCHAR(30) NOT NULL,
            unit VARCHAR(50),
            group_name VARCHAR(100),
            filterable BOOLEAN NOT NULL DEFAULT FALSE,
            comparable BOOLEAN NOT NULL DEFAULT TRUE,
            display_order INTEGER NOT NULL DEFAULT 0,
            aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
            normalization_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT attribute_definitions_category_key UNIQUE(category_id, attribute_key),
            CONSTRAINT attribute_definitions_data_type_check CHECK (
                data_type IN ('text','number','boolean','array','range','object')),
            CONSTRAINT attribute_definitions_aliases_array_check CHECK (jsonb_typeof(aliases) = 'array')
        )"""
    )
    op.execute("CREATE INDEX idx_attribute_definitions_category ON attribute_definitions(category_id)")
    op.execute(
        """CREATE TABLE product_attribute_values (
            product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            attribute_id BIGINT NOT NULL REFERENCES attribute_definitions(id) ON DELETE CASCADE,
            raw_value TEXT,
            value_text TEXT,
            value_number NUMERIC,
            value_boolean BOOLEAN,
            value_json JSONB,
            unit VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(product_id, attribute_id),
            CONSTRAINT product_attribute_values_typed_check CHECK (
                raw_value IS NULL OR btrim(raw_value) = '' OR
                num_nonnulls(value_text, value_number, value_boolean, value_json) >= 1)
        )"""
    )
    op.execute(
        "CREATE INDEX idx_attribute_numeric_filter ON product_attribute_values(attribute_id, value_number) "
        "WHERE value_number IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_attribute_text_filter ON product_attribute_values(attribute_id, value_text) "
        "WHERE value_text IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_attribute_boolean_filter ON product_attribute_values(attribute_id, value_boolean) "
        "WHERE value_boolean IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_attribute_json_gin ON product_attribute_values USING GIN(value_json) "
        "WHERE value_json IS NOT NULL"
    )

    dimension = _embedding_dimension()
    op.execute("CREATE SCHEMA IF NOT EXISTS policy_rag")
    op.execute(
        """CREATE TABLE policy_rag.policy_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_path TEXT NOT NULL UNIQUE,
            title TEXT,
            checksum VARCHAR(128) NOT NULL UNIQUE,
            document_type VARCHAR(100),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        f"""CREATE TABLE policy_rag.policy_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL REFERENCES policy_rag.policy_documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            embedding vector({dimension}),
            embedding_model VARCHAR(150),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(document_id, chunk_index)
        )"""
    )
    op.execute(
        """INSERT INTO policy_rag.policy_documents(
            source_path, title, checksum, document_type, metadata, created_at, updated_at)
        SELECT source_path, title, checksum, 'markdown', '{}'::jsonb, indexed_at, indexed_at
        FROM policy_rag.documents
        ON CONFLICT (source_path) DO NOTHING"""
    )
    op.execute(
        """INSERT INTO policy_rag.policy_chunks(
            document_id, chunk_index, content, token_count, metadata, embedding, embedding_model)
        SELECT d.id, c.chunk_index, c.content,
            cardinality(regexp_split_to_array(btrim(c.content), '\\s+')),
            jsonb_build_object(
                'legacy_id', c.id,
                'document_checksum', c.document_checksum,
                'title', c.title,
                'heading', c.heading,
                'line_start', c.line_start,
                'line_end', c.line_end),
            c.embedding, im.embedding_model
        FROM policy_rag.chunks c
        JOIN policy_rag.policy_documents d ON d.source_path = c.source_path
        LEFT JOIN policy_rag.index_metadata im ON im.singleton
        ON CONFLICT (document_id, chunk_index) DO NOTHING"""
    )
    op.execute("CREATE INDEX idx_policy_chunks_document_id ON policy_rag.policy_chunks(document_id)")
    op.execute(
        "CREATE INDEX idx_policy_chunks_embedding_hnsw ON policy_rag.policy_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS policy_rag.policy_chunks")
    op.execute("DROP TABLE IF EXISTS policy_rag.policy_documents")
    op.execute("DROP TABLE IF EXISTS product_attribute_values")
    op.execute("DROP TABLE IF EXISTS attribute_definitions")
    op.execute("DROP TABLE IF EXISTS product_offers")
    op.execute("DROP TABLE IF EXISTS raw_product_rows")
    op.execute("DROP TABLE IF EXISTS import_batches")

    op.execute("DROP INDEX IF EXISTS idx_product_specs_search_text")
    op.execute("DROP INDEX IF EXISTS idx_product_specs_normalized_gin")
    op.execute("DROP INDEX IF EXISTS idx_product_specs_raw_gin")
    op.execute("ALTER TABLE product_specs DROP CONSTRAINT IF EXISTS product_specs_pkey")
    op.execute("ALTER TABLE product_specs DROP CONSTRAINT IF EXISTS product_specs_legacy_id_key")
    op.execute("ALTER TABLE product_specs ADD CONSTRAINT product_specs_pkey PRIMARY KEY (id)")
    op.execute("ALTER TABLE product_specs ADD CONSTRAINT product_specs_product_id_key UNIQUE (product_id)")
    for column in ("updated_at", "created_at", "search_text", "normalized_specs", "raw_specs"):
        op.execute(f"ALTER TABLE product_specs DROP COLUMN IF EXISTS {column}")

    for index in (
        "idx_products_category_brand",
        "idx_products_status",
        "idx_products_model_code",
        "idx_products_brand_id",
        "idx_products_category_id",
        "products_product_web_id_key",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")
    for column in (
        "source_data",
        "status",
        "display_name",
        "brand_id",
        "model_code",
        "product_web_id",
    ):
        op.execute(f"ALTER TABLE products DROP COLUMN IF EXISTS {column}")
    op.execute("DROP TABLE IF EXISTS brands")
    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_code_key")
    for column in ("updated_at", "created_at", "is_active", "description", "code"):
        op.execute(f"ALTER TABLE categories DROP COLUMN IF EXISTS {column}")
