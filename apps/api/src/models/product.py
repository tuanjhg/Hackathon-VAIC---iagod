from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.category import Category
    from src.models.hybrid_catalog import Brand, ProductOffer
    from src.models.inventory import Inventory
    from src.models.price import Price
    from src.models.promotion import Promotion


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    product_web_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    model_code: Mapped[str | None] = mapped_column(String(150), index=True, nullable=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    brand: Mapped[str] = mapped_column(String(80), index=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), ForeignKey("categories.id"), index=True
    )
    brand_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), ForeignKey("brands.id"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    source_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    short_description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(String(500))
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    specifications: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="products")
    brand_entity: Mapped["Brand | None"] = relationship(back_populates="products")
    specs: Mapped["ProductSpec"] = relationship(
        back_populates="product", cascade="all, delete-orphan", uselist=False
    )
    price: Mapped["Price"] = relationship(
        back_populates="product", cascade="all, delete-orphan", uselist=False
    )
    inventory: Mapped["Inventory"] = relationship(
        back_populates="product", cascade="all, delete-orphan", uselist=False
    )
    promotion: Mapped["Promotion | None"] = relationship(
        back_populates="product", cascade="all, delete-orphan", uselist=False
    )
    offers: Mapped[list["ProductOffer"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductSpec(Base):
    __tablename__ = "product_specs"

    product_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    raw_specs: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    normalized_specs: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Compatibility facets used by the existing air-conditioner UI.
    capacity_btu: Mapped[int] = mapped_column(Integer, default=0)
    horsepower: Mapped[float] = mapped_column(Float, default=0)
    recommended_area_min: Mapped[int] = mapped_column(Integer, default=0)
    recommended_area_max: Mapped[int] = mapped_column(Integer, default=0)
    inverter: Mapped[bool] = mapped_column(Boolean, default=False)
    noise_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_rating: Mapped[str] = mapped_column(String(60), default="Chưa có dữ liệu")
    warranty_months: Mapped[int] = mapped_column(Integer, default=0)
    product: Mapped[Product] = relationship(back_populates="specs")
