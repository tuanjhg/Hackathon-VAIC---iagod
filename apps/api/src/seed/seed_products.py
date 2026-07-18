import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import SessionLocal
from src.models import Category, Inventory, Price, Product, ProductSpec, Promotion

logger = logging.getLogger(__name__)


def seed_products(db: Session, data: list[dict[str, Any]]) -> int:
    category = db.scalar(select(Category).where(Category.slug == "may-lanh"))
    if category is None:
        category = Category(code="air_conditioners", name="Máy lạnh", slug="may-lanh")
        db.add(category)
        db.flush()
    created = 0
    for item in data:
        if db.scalar(select(Product).where(Product.sku == item["sku"])):
            continue
        product = Product(
            id=item["id"], sku=item["sku"], slug=item["slug"], name=item["name"],
            brand=item["brand"], category=category, short_description=item["short_description"],
            image_url=item["image_url"], featured=item["featured"], rating=item["rating"],
            review_count=item["review_count"], display_name=item["name"], source_data={},
        )
        product.specs = ProductSpec(
            raw_specs={}, normalized_specs={},
            capacity_btu=item["capacity_btu"], horsepower=item["horsepower"],
            recommended_area_min=item["recommended_area_min"],
            recommended_area_max=item["recommended_area_max"], inverter=item["inverter"],
            noise_db=item["noise_db"], energy_rating=item["energy_rating"],
            warranty_months=item["warranty_months"],
        )
        product.price = Price(original_price=item["original_price"], sale_price=item["sale_price"], currency="VND")
        product.inventory = Inventory(stock_status=item["stock_status"], stock_quantity=item["stock_quantity"])
        if item.get("promotion"):
            product.promotion = Promotion(title=item["promotion"]["title"], description=item["promotion"]["description"])
        db.add(product)
        created += 1
    db.commit()
    return created


def main() -> None:
    path = Path(settings.products_data_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        created = seed_products(db, data)
    logger.info("Seeded %s products", created)
    print(f"Seed complete: {created} new products")


if __name__ == "__main__":
    main()
