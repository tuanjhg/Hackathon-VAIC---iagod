from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.repositories.product_repository import ProductRepository
from src.schemas.common import PaginatedResponse
from src.schemas.product import ProductRead
from src.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=PaginatedResponse[ProductRead])
def list_products(
    search: str | None = None,
    brand: str | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    room_area: float | None = Query(default=None, gt=0),
    inverter: bool | None = None,
    in_stock: bool | None = None,
    sort: Literal["featured", "price_asc", "price_desc"] = "featured",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProductRead]:
    return ProductService(ProductRepository(db)).list_products(
        search=search,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        room_area=room_area,
        inverter=inverter,
        in_stock=in_stock,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/{slug}", response_model=ProductRead)
def get_product(slug: str, db: Session = Depends(get_db)) -> ProductRead:
    return ProductService(ProductRepository(db)).get_product(slug)

