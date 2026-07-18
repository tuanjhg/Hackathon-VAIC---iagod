from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database import SessionLocal
from src.importers.category_registry import CATEGORY_REGISTRY
from src.importers.normalizers.common import normalize_brand
from src.models import AttributeDefinition, Brand, Category

COMMON_BRANDS = (
    "Samsung",
    "LG",
    "Panasonic",
    "Daikin",
    "Toshiba",
    "Aqua",
    "Electrolux",
    "Sharp",
    "Casper",
    "Midea",
    "Apple",
    "Xiaomi",
    "Lenovo",
    "Dell",
    "HP",
    "Asus",
    "Acer",
)


def seed_catalog_metadata(db: Session) -> tuple[int, int, int]:
    """Idempotently seed categories, facet definitions and common brands."""

    category_count = attribute_count = brand_count = 0
    existing_categories = {item.code: item for item in db.scalars(select(Category))}
    categories: dict[str, Category] = {}
    for config in CATEGORY_REGISTRY.values():
        category = existing_categories.get(config.code)
        if category is None:
            category = Category(code=config.code, name=config.name, slug=config.slug)
            db.add(category)
            db.flush()
            category_count += 1
        else:
            category.name = config.name
            category.slug = config.slug
            category.is_active = True
        categories[config.code] = category
    db.flush()
    existing_definitions = {
        (item.category_id, item.attribute_key): item
        for item in db.scalars(select(AttributeDefinition))
    }
    for config in CATEGORY_REGISTRY.values():
        category = categories[config.code]
        for order, item in enumerate(config.attributes, start=1):
            definition = existing_definitions.get((category.id, item.key))
            if definition is None:
                definition = AttributeDefinition(
                    category_id=category.id,
                    attribute_key=item.key,
                    display_name=item.display_name,
                    data_type=item.data_type,
                )
                db.add(definition)
                attribute_count += 1
            definition.source_column = item.source_column
            definition.display_name = item.display_name
            definition.data_type = item.data_type
            definition.unit = item.unit
            definition.group_name = item.group_name
            definition.filterable = item.filterable
            definition.comparable = item.comparable
            definition.display_order = order
            definition.aliases = []
            definition.normalization_config = {
                "normalized_path": list(item.normalized_path),
            }

    existing_brands = {item.normalized_name: item for item in db.scalars(select(Brand))}
    for brand_name in COMMON_BRANDS:
        normalized = normalize_brand(brand_name)
        if normalized is None:
            continue
        canonical, normalized_name = normalized
        brand = existing_brands.get(normalized_name)
        if brand is None:
            db.add(Brand(name=canonical, normalized_name=normalized_name))
            brand_count += 1
    db.commit()
    return category_count, attribute_count, brand_count


def main() -> None:
    with SessionLocal() as db:
        categories, attributes, brands = seed_catalog_metadata(db)
    print(
        f"Seed complete: categories_created={categories} "
        f"attributes_created={attributes} brands_created={brands}"
    )


if __name__ == "__main__":
    main()
