"""Tests for specs enrichment of the 9 specs_raw-only categories."""

from decimal import Decimal

from src.importers.category_registry import CATEGORY_REGISTRY
from src.seed.enrich_specs import _RAW_CATEGORIES, parsed_numeric_specs


def test_all_nine_raw_categories_are_mapped() -> None:
    assert set(_RAW_CATEGORIES) == {
        "tu_mat_dong", "man_hinh", "may_in", "may_nuoc_nong", "may_say",
        "may_tinh_bang", "micro_karaoke", "micro_thu_am", "pc_de_ban",
    }


def test_parsed_numeric_specs_coerces_decimal_and_drops_empty() -> None:
    config = CATEGORY_REGISTRY["desktop_computers"]
    row = {"ram": "16GB", "o_cung": "512GB SSD", "toc_do_cpu": "1.3 GHz", "so_nhan": "Không có"}
    out = parsed_numeric_specs(row, config)
    assert out["ram_gb"] == 16 and isinstance(out["ram_gb"], int)
    assert out["storage_gb"] == 512
    assert isinstance(out["cpu_base_clock_ghz"], float)
    assert not any(isinstance(v, Decimal) for v in out.values())
    assert "cpu_core_count" not in out  # "Không có" dropped


from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.core.database import Base  # noqa: E402
from src.models import Category, Product  # noqa: E402
from src.seed.enrich_specs import enrich_specs  # noqa: E402


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        cat = Category(code="pc_de_ban", name="PC", slug="pc")
        session.add(cat)
        session.flush()
        session.add(
            Product(
                sku="S1", slug="s1", name="PC S1", display_name="PC S1", brand="X",
                category_id=cat.id, category_key="pc_de_ban", short_description="PC S1",
                image_url="https://img.example/s1.jpg",
                specs_json={"display_name": "PC S1"},
            )
        )
        session.commit()
        yield session


def test_enrich_merges_parsed_specs_by_sku(db: Session, tmp_path: Path) -> None:
    csv = tmp_path / "pc_de_ban.csv"
    csv.write_text("sku,ram,o cung,toc do cpu\nS1,16GB,512GB SSD,1.3 GHz\n", encoding="utf-8")

    report = enrich_specs(db, tmp_path)

    product = db.query(Product).filter_by(sku="S1").one()
    assert product.specs_json["ram_gb"] == 16
    assert product.specs_json["storage_gb"] == 512
    assert product.specs_json["display_name"] == "PC S1"  # preserved
    assert report["pc_de_ban"]["enriched"] == 1
