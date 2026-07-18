"""Multi-category JSON specs on Product.

Proves a product from a *different* category (tủ lạnh / refrigerator) — whose
spec shape does not match the máy-lạnh-only ``ProductSpec`` table — can be stored
in the generic nullable JSON columns with NO ``ProductSpec`` row at all, and that
the JSON round-trips through the DB intact.

The existing máy-lạnh demo flow is proved untouched by the rest of the suite
(``test_products.py`` / ``test_chat.py``), which still seeds the typed
``ProductSpec`` relationship exactly as before.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.models import Category, Product, ProductSpec

# tủ lạnh (refrigerator) structured spec shape — completely different from the
# máy-lạnh ProductSpec columns (capacity_btu, horsepower, ...).
TU_LANH_SPECS = {
    "display_name": "Panasonic Inverter 313 lít NR-BL340",
    "capacity_total_l": 313.0,
    "capacity_freezer_l": 92.0,
    "recommended_people_min": 3.0,
    "recommended_people_max": 4.0,
    "inverter": True,
    "doors": 2,
    "style": "Ngăn đá trên",
    "made_in": "Việt Nam",
}
TU_LANH_SPECS_RAW = {
    "Dung tích": "313 lít",
    "Kiểu tủ": "2 cửa",
    "Công nghệ": "Inverter tiết kiệm điện",
}


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    # Same in-memory SQLite pattern as tests/conftest.py: a single shared
    # connection (StaticPool) so separate sessions see the same database.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        yield db
    Base.metadata.drop_all(engine)


def _make_tu_lanh(db: Session) -> int:
    category = Category(code="tu_lanh", name="Tủ lạnh", slug="tu-lanh")
    product = Product(
        sku="1751098000999",
        slug="panasonic-nr-bl340-313l",
        name="Panasonic Inverter 313 lít NR-BL340",
        display_name="Panasonic Inverter 313 lít NR-BL340",
        brand="Panasonic",
        category=category,
        category_key="tu_lanh",
        short_description="Tủ lạnh 2 cửa 313 lít",
        image_url="https://example.com/nr-bl340.jpg",
        specs_json=TU_LANH_SPECS,
        specs_raw=TU_LANH_SPECS_RAW,
        # NOTE: no ProductSpec assigned — that relationship is optional at the DB
        # level (no NOT NULL constraint forcing a row per Product).
    )
    db.add(product)
    db.commit()
    return product.id


def test_new_category_product_roundtrips_json_without_productspec(session: Session) -> None:
    product_id = _make_tu_lanh(session)

    # Read back from the DB in a fresh session so we prove the JSON survived a
    # real serialize -> store -> deserialize round-trip, not the identity map.
    fresh = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    with fresh() as db:
        loaded = db.get(Product, product_id)
        assert loaded is not None

        # Generic multi-category columns.
        assert loaded.category_key == "tu_lanh"
        assert loaded.specs_json is not None
        assert loaded.specs_raw is not None

        # Nested JSON values are intact and correctly typed (float stays float).
        assert loaded.specs_json["capacity_total_l"] == 313.0
        assert isinstance(loaded.specs_json["capacity_total_l"], float)
        assert loaded.specs_json["doors"] == 2
        assert loaded.specs_json["inverter"] is True
        assert loaded.specs_json["style"] == "Ngăn đá trên"
        assert loaded.specs_json == TU_LANH_SPECS
        assert loaded.specs_raw == TU_LANH_SPECS_RAW

        # No typed máy-lạnh ProductSpec row exists for this product.
        assert loaded.specs is None
        spec_count = db.scalar(
            select(func.count()).select_from(ProductSpec).where(
                ProductSpec.product_id == product_id
            )
        )
        assert spec_count == 0


def test_json_columns_are_nullable(session: Session) -> None:
    # A product may omit all three new columns (e.g. legacy rows / máy-lạnh demo).
    category = Category(code="may_lanh", name="Máy lạnh", slug="may-lanh")
    product = Product(
        sku="sku-no-json",
        slug="sku-no-json",
        name="No JSON specs",
        display_name="No JSON specs",
        brand="Daikin",
        category=category,
        short_description="x",
        image_url="https://example.com/x.jpg",
    )
    session.add(product)
    session.commit()

    assert product.category_key is None
    assert product.specs_json is None
    assert product.specs_raw is None


def test_specs_json_persists_to_specs_db_column(session: Session) -> None:
    # The ORM attribute is ``specs_json`` (``specs`` is the ProductSpec
    # relationship), but the underlying DB column is named ``specs``.
    assert Product.__table__.c["specs"].nullable is True
    assert "specs_json" not in Product.__table__.c

    product_id = _make_tu_lanh(session)
    row = session.execute(
        select(Product.__table__.c["specs"]).where(Product.__table__.c.id == product_id)
    ).one()
    assert row[0]["capacity_total_l"] == 313.0
