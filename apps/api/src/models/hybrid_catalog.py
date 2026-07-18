from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.category import Category
    from src.models.product import Product

BIGINT = BigInteger().with_variant(Integer, "sqlite")
JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    normalized_name: Mapped[str] = mapped_column(String(150), unique=True)
    source_brand_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    products: Mapped[list[Product]] = relationship(back_populates="brand_entity")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','completed','completed_with_errors','failed')",
            name="import_batches_status_check",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    source_file: Mapped[str] = mapped_column(String(500))
    category_code: Mapped[str] = mapped_column(String(100), index=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rows: Mapped[list[RawProductRow]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class RawProductRow(Base):
    __tablename__ = "raw_product_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="raw_product_rows_batch_row_key"),
        CheckConstraint(
            "import_status IN ('pending','processing','imported','skipped','failed')",
            name="raw_product_rows_status_check",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("import_batches.id", ondelete="CASCADE")
    )
    row_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    import_status: Mapped[str] = mapped_column(String(30), default="pending")
    product_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("products.id"), nullable=True, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    batch: Mapped[ImportBatch] = relationship(back_populates="rows")


class ProductOffer(Base):
    __tablename__ = "product_offers"
    __table_args__ = (
        CheckConstraint("original_price IS NULL OR original_price >= 0"),
        CheckConstraint("sale_price IS NULL OR sale_price >= 0"),
        CheckConstraint(
            "original_price IS NULL OR sale_price IS NULL OR sale_price <= original_price"
        ),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from"),
        Index(
            "idx_one_current_offer_per_product",
            "product_id",
            unique=True,
            postgresql_where=text("is_current = TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    gifts: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, default=list)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    product: Mapped[Product] = relationship(back_populates="offers")


class AttributeDefinition(Base):
    __tablename__ = "attribute_definitions"
    __table_args__ = (
        UniqueConstraint("category_id", "attribute_key"),
        CheckConstraint(
            "data_type IN ('text','number','boolean','array','range','object')",
            name="attribute_definitions_data_type_check",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    attribute_key: Mapped[str] = mapped_column(String(150))
    source_column: Mapped[str | None] = mapped_column(String(150), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    data_type: Mapped[str] = mapped_column(String(30))
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filterable: Mapped[bool] = mapped_column(Boolean, default=False)
    comparable: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    aliases: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list)
    normalization_config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    category: Mapped[Category] = relationship()
    values: Mapped[list[ProductAttributeValue]] = relationship(
        back_populates="attribute", cascade="all, delete-orphan"
    )


class ProductAttributeValue(Base):
    __tablename__ = "product_attribute_values"
    __table_args__ = (
        CheckConstraint(
            "raw_value IS NULL OR trim(raw_value) = '' OR "
            "value_text IS NOT NULL OR value_number IS NOT NULL OR "
            "value_boolean IS NOT NULL OR value_json IS NOT NULL",
            name="product_attribute_values_typed_check",
        ),
        Index(
            "idx_attribute_numeric_filter",
            "attribute_id",
            "value_number",
            postgresql_where=text("value_number IS NOT NULL"),
        ),
        Index(
            "idx_attribute_text_filter",
            "attribute_id",
            "value_text",
            postgresql_where=text("value_text IS NOT NULL"),
        ),
        Index(
            "idx_attribute_boolean_filter",
            "attribute_id",
            "value_boolean",
            postgresql_where=text("value_boolean IS NOT NULL"),
        ),
    )

    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    attribute_id: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey("attribute_definitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_json: Mapped[Any | None] = mapped_column(JSON_VALUE, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    attribute: Mapped[AttributeDefinition] = relationship(back_populates="values")
