from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    slug: str
    description: str | None = None
    is_active: bool


class PromotionRead(BaseModel):
    title: str
    description: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class ProductRead(BaseModel):
    id: int
    sku: str
    slug: str
    name: str
    brand: str
    category: str
    category_slug: str
    original_price: Decimal
    sale_price: Decimal
    currency: str
    capacity_btu: int
    horsepower: float
    recommended_area_min: int
    recommended_area_max: int
    inverter: bool
    noise_db: float | None
    energy_rating: str
    warranty_months: int
    stock_status: str
    stock_quantity: int
    promotion: PromotionRead | None
    short_description: str
    image_url: str
    rating: float
    review_count: int
    featured: bool
    specifications: dict[str, object]


class ComparisonResponse(BaseModel):
    products: list[ProductRead]
    best_price_id: int | None
    quietest_id: int | None
    best_overall_id: int | None


class FacetFilter(BaseModel):
    eq: str | int | float | bool | list[object] | None = None
    gte: float | None = None
    lte: float | None = None
    in_values: list[str | int | float | bool] | None = Field(default=None, alias="in")


class ProductSort(BaseModel):
    field: str
    direction: str = Field(pattern="^(asc|desc)$")


class ProductSearchRequest(BaseModel):
    category_code: str
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    filters: dict[str, FacetFilter] = Field(default_factory=dict)
    sort: list[ProductSort] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ProductSearchResponse(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int
