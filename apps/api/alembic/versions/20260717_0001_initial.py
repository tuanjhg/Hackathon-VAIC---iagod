"""initial schema"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("categories", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False, unique=True), sa.Column("slug", sa.String(120), nullable=False, unique=True))
    op.create_index("ix_categories_slug", "categories", ["slug"])
    op.create_table("products", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("sku", sa.String(60), nullable=False, unique=True), sa.Column("slug", sa.String(180), nullable=False, unique=True), sa.Column("name", sa.String(240), nullable=False), sa.Column("brand", sa.String(80), nullable=False), sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False), sa.Column("short_description", sa.Text(), nullable=False), sa.Column("image_url", sa.String(500), nullable=False), sa.Column("featured", sa.Boolean(), nullable=False), sa.Column("rating", sa.Float(), nullable=False), sa.Column("review_count", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_slug", "products", ["slug"])
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_table("product_specs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, unique=True), sa.Column("capacity_btu", sa.Integer(), nullable=False), sa.Column("horsepower", sa.Float(), nullable=False), sa.Column("recommended_area_min", sa.Integer(), nullable=False), sa.Column("recommended_area_max", sa.Integer(), nullable=False), sa.Column("inverter", sa.Boolean(), nullable=False), sa.Column("noise_db", sa.Float(), nullable=True), sa.Column("energy_rating", sa.String(60), nullable=False), sa.Column("warranty_months", sa.Integer(), nullable=False))
    op.create_table("prices", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, unique=True), sa.Column("original_price", sa.Numeric(14, 2), nullable=False), sa.Column("sale_price", sa.Numeric(14, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("inventory", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, unique=True), sa.Column("stock_status", sa.String(30), nullable=False), sa.Column("stock_quantity", sa.Integer(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_inventory_stock_status", "inventory", ["stock_status"])
    op.create_table("promotions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, unique=True), sa.Column("title", sa.String(180), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True), sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_table("promotions")
    op.drop_table("inventory")
    op.drop_table("prices")
    op.drop_table("product_specs")
    op.drop_table("products")
    op.drop_table("categories")

