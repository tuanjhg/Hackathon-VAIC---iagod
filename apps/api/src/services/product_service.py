import math
from decimal import Decimal

from fastapi import HTTPException, status

from src.models import Product
from src.repositories.product_repository import ProductRepository
from src.schemas.common import PaginatedResponse
from src.schemas.product import (
    ProductRead,
    ProductSearchRequest,
    ProductSearchResponse,
    PromotionRead,
)


def serialize_product(product: Product) -> ProductRead:
    current_offer = next((offer for offer in product.offers if offer.is_current), None)
    original_price = (
        current_offer.original_price
        if current_offer and current_offer.original_price is not None
        else product.price.original_price
    )
    sale_price = (
        current_offer.sale_price
        if current_offer and current_offer.sale_price is not None
        else product.price.sale_price
    )
    return ProductRead(
        id=product.id,
        sku=product.sku,
        slug=product.slug,
        name=product.name,
        brand=product.brand,
        category=product.category.name,
        category_slug=product.category.slug,
        original_price=original_price,
        sale_price=sale_price,
        currency=current_offer.currency if current_offer else product.price.currency,
        capacity_btu=product.specs.capacity_btu,
        horsepower=product.specs.horsepower,
        recommended_area_min=product.specs.recommended_area_min,
        recommended_area_max=product.specs.recommended_area_max,
        inverter=product.specs.inverter,
        noise_db=product.specs.noise_db,
        energy_rating=product.specs.energy_rating,
        warranty_months=product.specs.warranty_months,
        stock_status=product.inventory.stock_status,
        stock_quantity=product.inventory.stock_quantity,
        promotion=(
            PromotionRead(
                title=product.promotion.title,
                description=product.promotion.description,
                valid_from=product.promotion.valid_from,
                valid_to=product.promotion.valid_to,
            )
            if product.promotion
            else None
        ),
        short_description=product.short_description,
        image_url=product.image_url,
        rating=product.rating,
        review_count=product.review_count,
        featured=product.featured,
        specifications=product.specs.raw_specs or product.specifications,
    )


class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def list_products(self, **filters: object) -> PaginatedResponse[ProductRead]:
        page_value = filters.get("page", 1)
        page_size_value = filters.get("page_size", 12)
        if not isinstance(page_value, int) or not isinstance(page_size_value, int):
            raise TypeError("page and page_size must be integers")
        page = page_value
        page_size = page_size_value
        products, total = self.repository.list_products(**filters)  # type: ignore[arg-type]
        return PaginatedResponse(
            items=[serialize_product(product) for product in products],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    def get_product(self, slug: str) -> ProductRead:
        product = self.repository.get_by_identifier(slug)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return serialize_product(product)

    def search_products(self, request: ProductSearchRequest) -> ProductSearchResponse:
        try:
            products, total = self.repository.search_facets(request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return ProductSearchResponse(
            items=[serialize_product(product) for product in products],
            total=total,
            limit=request.limit,
            offset=request.offset,
        )

    def products_for_need(
        self, room_area: float, budget_max: int | None, priority: str
    ) -> list[Product]:
        products, _ = self.repository.list_products(
            room_area=room_area,
            max_price=Decimal(budget_max) if budget_max else None,
            in_stock=True,
            page_size=50,
        )
        if len(products) < 3:
            products, _ = self.repository.list_products(
                max_price=Decimal(budget_max) if budget_max else None,
                page_size=50,
            )
        if priority == "Chạy êm":
            products.sort(key=lambda p: p.specs.noise_db if p.specs.noise_db is not None else 999)
        elif priority == "Giá tốt":
            products.sort(key=lambda p: p.price.sale_price if p.price.sale_price > 0 else Decimal("Infinity"))
        elif priority == "Tiết kiệm điện":
            products.sort(key=lambda p: (not p.specs.inverter, p.price.sale_price))
        elif priority == "Làm lạnh nhanh":
            products.sort(key=lambda p: p.specs.capacity_btu, reverse=True)
        return products[:3]
