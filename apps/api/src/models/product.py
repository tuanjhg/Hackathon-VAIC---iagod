from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.category import Category
    from src.models.inventory import Inventory
    from src.models.price import Price
    from src.models.promotion import Promotion


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    brand: Mapped[str] = mapped_column(String(80), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    short_description: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(String(500))
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    # Multi-category catalog fields (nullable). Populated by the generalized ETL
    # loader for the 14 real categories; the máy-lạnh demo flow leaves these NULL
    # and continues to use the typed ``ProductSpec`` relationship below.
    #
    # NOTE: the JSON structured-spec column is named ``specs`` in the database
    # (matching the ETL record key), but is exposed on the ORM as ``specs_json``
    # because the attribute name ``specs`` is already taken by the ProductSpec
    # relationship (see below), which the demo flow depends on.
    category_key: Mapped[str | None] = mapped_column(String, nullable=True)
    specs_json: Mapped[dict[str, Any] | None] = mapped_column(
        "specs", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    specs_raw: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="products")
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


class ProductSpec(Base):
    __tablename__ = "product_specs"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True)
    capacity_btu: Mapped[int] = mapped_column(Integer)
    horsepower: Mapped[float] = mapped_column(Float)
    recommended_area_min: Mapped[int] = mapped_column(Integer)
    recommended_area_max: Mapped[int] = mapped_column(Integer)
    inverter: Mapped[bool] = mapped_column(Boolean)
    noise_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_rating: Mapped[str] = mapped_column(String(60))
    warranty_months: Mapped[int] = mapped_column(Integer)
    product: Mapped[Product] = relationship(back_populates="specs")
