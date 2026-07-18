"""Add flexible specifications for the full multi-category catalog.

Revision ID: 20260718_0004
Revises: 20260718_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260718_0004"
down_revision: str | None = "20260718_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = (
        postgresql.JSONB(astext_type=sa.Text())
        if op.get_bind().dialect.name == "postgresql"
        else sa.JSON()
    )
    op.add_column(
        "products",
        sa.Column("specifications", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "ix_products_specifications_gin",
            "products",
            ["specifications"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_products_specifications_gin", table_name="products")
    op.drop_column("products", "specifications")
