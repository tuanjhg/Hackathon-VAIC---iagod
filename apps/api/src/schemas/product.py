from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str


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


class ComparisonResponse(BaseModel):
    products: list[ProductRead]
    best_price_id: int | None
    quietest_id: int | None
    best_overall_id: int | None

