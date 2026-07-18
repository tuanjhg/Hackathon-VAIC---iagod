"""seed_realdata tests (task 14) — idempotency, honest price/inventory
handling, and category-row reuse with the existing aircon demo seed.
"""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.models import Category, Product
from src.seed.seed_realdata import seed_realdata


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def categories_dir(tmp_path: Path) -> Path:
    may_lanh = [
        {
            "sku": "SKU-ML-1",
            "category_key": "may_lanh",
            "category_label": "Máy lạnh",
            "brand": "Daikin",
            "model_code": "M001",
            "original_price": 11_000_000,
            "sale_price": 10_500_000,
            "has_price_data": True,
            "promotions": ["Miễn phí lắp đặt"],
            "specs_raw": {"Công suất": "1 HP"},
            "specs": {"display_name": "Daikin Máy lạnh (mã M001)"},
        },
        {
            "sku": "SKU-ML-2",
            "category_key": "may_lanh",
            "category_label": "Máy lạnh",
            "brand": "LG",
            "model_code": "M002",
            "original_price": None,
            "sale_price": None,
            "has_price_data": False,
            "promotions": [],
            "specs_raw": {},
            "specs": {"display_name": "LG Máy lạnh (mã M002)"},
        },
    ]
    tu_mat = [
        {
            "sku": "SKU-TM-1",
            "category_key": "tu_mat_dong",
            "category_label": "Tủ mát, tủ đông",
            "brand": "Hoà Phát",
            "model_code": "T001",
            "original_price": 10_300_000,
            "sale_price": 10_300_000,
            "has_price_data": True,
            "promotions": [],
            "specs_raw": {"Loại sản phẩm": "Tủ mát"},
            "specs": {"display_name": "Hoà Phát Tủ mát, tủ đông (mã T001)"},
        }
    ]
    (tmp_path / "may_lanh.json").write_text(json.dumps(may_lanh), encoding="utf-8")
    (tmp_path / "tu_mat_dong.json").write_text(json.dumps(tu_mat), encoding="utf-8")
    (tmp_path / "_summary.json").write_text(json.dumps({"skip": "me"}), encoding="utf-8")
    return tmp_path


def test_seeds_all_products_across_categories(db: Session, categories_dir: Path) -> None:
    created = seed_realdata(db, categories_dir)
    assert created == 3
    assert db.scalar(select(Product).where(Product.sku == "SKU-ML-1")) is not None
    assert db.scalar(select(Product).where(Product.sku == "SKU-TM-1")) is not None


def test_price_row_only_when_has_price_data(db: Session, categories_dir: Path) -> None:
    seed_realdata(db, categories_dir)
    priced = db.scalar(select(Product).where(Product.sku == "SKU-ML-1"))
    unpriced = db.scalar(select(Product).where(Product.sku == "SKU-ML-2"))
    assert priced is not None and priced.price is not None
    assert priced.price.sale_price == 10_500_000
    assert unpriced is not None and unpriced.price is None


def test_no_inventory_row_created(db: Session, categories_dir: Path) -> None:
    seed_realdata(db, categories_dir)
    product = db.scalar(select(Product).where(Product.sku == "SKU-ML-1"))
    assert product is not None
    assert product.inventory is None


def test_specs_json_and_raw_populated(db: Session, categories_dir: Path) -> None:
    seed_realdata(db, categories_dir)
    product = db.scalar(select(Product).where(Product.sku == "SKU-ML-1"))
    assert product is not None
    assert product.category_key == "may_lanh"
    assert product.specs_json == {"display_name": "Daikin Máy lạnh (mã M001)"}
    assert product.specs_raw == {"Công suất": "1 HP"}


def test_idempotent_on_rerun(db: Session, categories_dir: Path) -> None:
    first = seed_realdata(db, categories_dir)
    second = seed_realdata(db, categories_dir)
    assert first == 3
    assert second == 0
    assert db.scalar(select(Product).where(Product.sku == "SKU-ML-1")) is not None


def test_enriches_existing_normalized_product_for_ai_search(
    db: Session, categories_dir: Path
) -> None:
    category = Category(code="air_conditioners", name="Máy lạnh", slug="may-lanh")
    db.add(category)
    existing = Product(
        sku="SKU-ML-1",
        slug="existing-sku-ml-1",
        name="Existing product",
        display_name="Existing product",
        brand="Daikin",
        category=category,
        short_description="Existing",
        image_url="",
        category_key=None,
        specs_json=None,
        specs_raw=None,
    )
    db.add(existing)
    db.commit()

    assert seed_realdata(db, categories_dir) == 2
    db.refresh(existing)
    assert existing.category_key == "may_lanh"
    assert existing.specs_json == {"display_name": "Daikin Máy lạnh (mã M001)"}
    assert existing.specs_raw == {"Công suất": "1 HP"}


def test_reuses_existing_category_row_when_slug_matches(db: Session, categories_dir: Path) -> None:
    existing = Category(code="air_conditioners", name="Máy lạnh", slug="may-lanh")
    db.add(existing)
    db.flush()
    existing_id = existing.id

    seed_realdata(db, categories_dir)

    categories = db.scalars(select(Category).where(Category.slug == "may-lanh")).all()
    assert len(categories) == 1
    product = db.scalar(select(Product).where(Product.sku == "SKU-ML-1"))
    assert product is not None
    assert product.category_id == existing_id


def test_reuses_normalized_category_when_name_matches_but_slug_differs(
    db: Session, categories_dir: Path
) -> None:
    existing = Category(
        code="coolers_freezers",
        name="Tủ mát, tủ đông",
        slug="tu-mat-tu-dong",
    )
    db.add(existing)
    db.flush()
    existing_id = existing.id

    seed_realdata(db, categories_dir)

    categories = db.scalars(
        select(Category).where(Category.name == "Tủ mát, tủ đông")
    ).all()
    assert len(categories) == 1
    product = db.scalar(select(Product).where(Product.sku == "SKU-TM-1"))
    assert product is not None
    assert product.category_id == existing_id


def test_summary_file_is_skipped(db: Session, categories_dir: Path) -> None:
    created = seed_realdata(db, categories_dir)
    assert created == 3  # not 4 -- _summary.json must not be treated as a category


def test_sequence_resync_is_a_noop_on_sqlite(db: Session, categories_dir: Path) -> None:
    # Regression guard: on Postgres, seeding after seed_products.py's
    # explicit-id inserts previously collided on products_id_seq (id=1
    # already taken) -- this only surfaces against a real Postgres sequence,
    # so this just asserts the SQLite no-op path doesn't raise.
    from src.seed.seed_realdata import _resync_postgres_id_sequence

    _resync_postgres_id_sequence(db)
    assert seed_realdata(db, categories_dir) == 3
