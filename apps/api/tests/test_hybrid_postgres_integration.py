"""Optional PostgreSQL integration checks for the deployed hybrid schema.

Set ``HYBRID_TEST_DATABASE_URL`` to a disposable or staging PostgreSQL database
that has already run ``alembic upgrade head``. The normal unit-test suite does
not silently connect to production.
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, text

DATABASE_URL = os.getenv("HYBRID_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="HYBRID_TEST_DATABASE_URL is not configured",
)


def test_postgres_extensions_tables_constraints_and_indexes() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    inspector = inspect(engine)

    expected_tables = {
        "import_batches",
        "raw_product_rows",
        "categories",
        "brands",
        "products",
        "product_specs",
        "product_offers",
        "attribute_definitions",
        "product_attribute_values",
    }
    assert expected_tables <= set(inspector.get_table_names())
    assert {"policy_documents", "policy_chunks"} <= set(
        inspector.get_table_names(schema="policy_rag")
    )

    with engine.connect() as connection:
        extensions = set(
            connection.execute(
                text(
                    "SELECT extname FROM pg_extension "
                    "WHERE extname IN ('vector', 'pgcrypto')"
                )
            ).scalars()
        )
        assert extensions == {"vector", "pgcrypto"}

        index_names = set(
            connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema()"
                )
            ).scalars()
        )
        assert {
            "idx_product_specs_raw_gin",
            "idx_product_specs_normalized_gin",
            "idx_one_current_offer_per_product",
            "idx_attribute_numeric_filter",
            "idx_attribute_text_filter",
            "idx_attribute_boolean_filter",
            "idx_attribute_json_gin",
        } <= index_names

        policy_index_names = set(
            connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'policy_rag'"
                )
            ).scalars()
        )
        assert "idx_policy_chunks_embedding_hnsw" in policy_index_names

        constraint_names = set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE connamespace = current_schema()::regnamespace"
                )
            ).scalars()
        )
        assert {
            "import_batches_status_check",
            "attribute_definitions_data_type_check",
            "product_attribute_values_typed_check",
        } <= constraint_names

    engine.dispose()
