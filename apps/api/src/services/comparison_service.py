from fastapi import HTTPException, status

from src.repositories.product_repository import ProductRepository
from src.schemas.product import ComparisonResponse
from src.services.product_service import serialize_product


class ComparisonService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def compare(self, product_ids: list[int]) -> ComparisonResponse:
        if len(set(product_ids)) != len(product_ids):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Duplicate ids")
        products = self.repository.get_by_ids(product_ids)
        if len(products) != len(product_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        available_noise = [p for p in products if p.specs.noise_db is not None]
        priced_products = [p for p in products if p.price.sale_price > 0]
        best_price = min(priced_products, key=lambda p: p.price.sale_price) if priced_products else None
        quietest = min(available_noise, key=lambda p: p.specs.noise_db or 999) if available_noise else None
        best_overall = max(
            products,
            key=lambda p: p.rating + (0.2 if p.specs.inverter else 0) + (0.1 if p.featured else 0),
        )
        return ComparisonResponse(
            products=[serialize_product(product) for product in products],
            best_price_id=best_price.id if best_price else None,
            quietest_id=quietest.id if quietest else None,
            best_overall_id=best_overall.id,
        )
