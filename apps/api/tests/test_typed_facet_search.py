from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.database import Base
from src.db.seed import seed_catalog_metadata
from src.models import (
    AttributeDefinition,
    Category,
    Inventory,
    Price,
    Product,
    ProductAttributeValue,
    ProductOffer,
    ProductSpec,
)
from src.repositories.product_repository import ProductRepository
from src.schemas.product import FacetFilter, ProductSearchRequest


def _add_product(
    db: Session,
    category_code: str,
    sku: str,
    price: int,
    facets: dict[str, Decimal | bool],
) -> Product:
    category = db.scalar(select(Category).where(Category.code == category_code))
    assert category is not None
    product = Product(
        sku=sku,
        slug=sku.lower(),
        name=sku,
        display_name=sku,
        brand="Test",
        category=category,
        short_description="Test",
        image_url="",
        featured=False,
        rating=0,
        review_count=0,
        source_data={},
    )
    product.specs = ProductSpec(raw_specs={}, normalized_specs={})
    product.price = Price(original_price=price, sale_price=price, currency="VND")
    product.inventory = Inventory(stock_status="unknown", stock_quantity=0)
    product.offers.append(
        ProductOffer(original_price=price, sale_price=price, gifts=[], is_current=True)
    )
    db.add(product)
    db.flush()
    for key, value in facets.items():
        definition = db.scalar(
            select(AttributeDefinition).where(
                AttributeDefinition.category_id == category.id,
                AttributeDefinition.attribute_key == key,
            )
        )
        assert definition is not None
        facet = ProductAttributeValue(
            product_id=product.id,
            attribute_id=definition.id,
            raw_value=str(value),
            unit=definition.unit,
        )
        if isinstance(value, bool):
            facet.value_boolean = value
        else:
            facet.value_number = value
        db.add(facet)
    return product


@pytest.fixture()
def catalog_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    seed_catalog_metadata(db)
    _add_product(
        db,
        "refrigerators",
        "RF-400",
        14_000_000,
        {"total_capacity_liter": Decimal(406), "inverter": True},
    )
    _add_product(
        db,
        "air_conditioners",
        "AC-20",
        12_000_000,
        {"recommended_area_min_m2": Decimal(15), "recommended_area_max_m2": Decimal(25)},
    )
    _add_product(
        db,
        "washing_machines",
        "WM-10",
        9_000_000,
        {"washing_capacity_kg": Decimal(10)},
    )
    _add_product(
        db,
        "tablets",
        "TAB-8",
        13_000_000,
        {"ram_gb": Decimal(8)},
    )
    db.commit()
    yield db
    db.close()


def test_filter_refrigerator_capacity_and_boolean(catalog_db: Session) -> None:
    products, total = ProductRepository(catalog_db).search_facets(
        ProductSearchRequest(
            category_code="refrigerators",
            price_max=Decimal(15_000_000),
            filters={
                "total_capacity_liter": FacetFilter(gte=300, lte=500),
                "inverter": FacetFilter(eq=True),
            },
        )
    )
    assert total == 1
    assert products[0].sku == "RF-400"


@pytest.mark.parametrize(
    ("category", "key", "minimum", "sku"),
    [
        ("air_conditioners", "recommended_area_max_m2", 20, "AC-20"),
        ("washing_machines", "washing_capacity_kg", 9, "WM-10"),
        ("tablets", "ram_gb", 8, "TAB-8"),
    ],
)
def test_filter_numeric_facets(
    catalog_db: Session, category: str, key: str, minimum: float, sku: str
) -> None:
    products, total = ProductRepository(catalog_db).search_facets(
        ProductSearchRequest(
            category_code=category,
            price_max=Decimal(15_000_000),
            filters={key: FacetFilter(gte=minimum)},
        )
    )
    assert total == 1
    assert products[0].sku == sku


def test_reject_unknown_facet(catalog_db: Session) -> None:
    with pytest.raises(ValueError, match="Unknown or non-filterable"):
        ProductRepository(catalog_db).search_facets(
            ProductSearchRequest(
                category_code="tablets", filters={"sql_injection": FacetFilter(eq="x")}
            )
        )
