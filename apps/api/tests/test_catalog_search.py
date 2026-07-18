"""catalog_search tool tests (ADR A5, STT10) — structured-first hard filter
half of stage S4 (docs/pipelines.md §6.4 point 1).

Uses the same in-memory SQLite pattern as tests/conftest.py (a single shared
connection via StaticPool so independent sessions see the same DB). Fixtures are
small inline Product rows across the ``may_lanh`` and ``tu_lanh`` categories with
varying ``specs_json`` capacity/area/people fields, some with a Price row and
some without, plus an unknown-category row and a legacy demo row
(``category_key is None``) to prove isolation.
"""

from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.models import Category, Price, Product
from src.tools.catalog_search import (
    TOOL_SCHEMA,
    CatalogSearchResult,
    catalog_count,
    catalog_search,
)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        _seed(db)
        yield db
    Base.metadata.drop_all(engine)


def _seed(db: Session) -> None:
    ml = Category(code="may_lanh", name="Máy lạnh", slug="may-lanh")
    tl = Category(code="tu_lanh", name="Tủ lạnh", slug="tu-lanh")
    misc = Category(code="quat_dieu_hoa", name="Quạt điều hòa", slug="quat-dieu-hoa")
    demo = Category(code="demo", name="Demo", slug="demo")
    db.add_all([ml, tl, misc, demo])

    products = [
        # --- máy lạnh ---
        _product(
            "ml_priced_ok",
            "Daikin FTKB35YVMV 1.5 HP Inverter",
            "Daikin",
            ml,
            "may_lanh",
            {"capacity_btu": 12000, "recommended_area_min": 15.0,
             "recommended_area_max": 20.0, "inverter": True},
            sale_price=10_000_000,
        ),
        _product(
            "ml_priced_over",
            "Panasonic XPU18 2 HP Inverter",
            "Panasonic",
            ml,
            "may_lanh",
            {"capacity_btu": 18000, "recommended_area_min": 18.0,
             "recommended_area_max": 30.0, "inverter": True},
            sale_price=25_000_000,
        ),
        _product(
            "ml_unpriced",
            "LG V13WIN1 1.5 HP",
            "LG",
            ml,
            "may_lanh",
            {"capacity_btu": 12000, "recommended_area_min": 15.0,
             "recommended_area_max": 20.0, "inverter": False},
        ),
        _product(
            "ml_small",
            "Toshiba RKCG10 1 HP",
            "Toshiba",
            ml,
            "may_lanh",
            {"capacity_btu": 9000, "recommended_area_min": 8.0,
             "recommended_area_max": 13.0, "inverter": False},
        ),
        # No area-range fields -> exercises the BTU-formula fallback branch.
        _product(
            "ml_btu_only",
            "Casper KC24 3 HP",
            "Casper",
            ml,
            "may_lanh",
            {"capacity_btu": 24000, "inverter": True},
        ),
        # --- tủ lạnh ---
        _product(
            "tl_big",
            "Samsung RT50 500 lít",
            "Samsung",
            tl,
            "tu_lanh",
            {"capacity_total_l": 500.0, "inverter": True, "style": "Ngăn đá trên"},
            sale_price=15_000_000,
        ),
        _product(
            "tl_small",
            "Aqua AQR-150 150 lít",
            "Aqua",
            tl,
            "tu_lanh",
            {"capacity_total_l": 150.0, "inverter": False, "style": "Ngăn đá trên"},
        ),
        _product(
            "tl_priced_over",
            "LG side-by-side 600 lít",
            "LG",
            tl,
            "tu_lanh",
            {"capacity_total_l": 600.0, "inverter": True, "style": "side_by_side"},
            sale_price=40_000_000,
        ),
        # --- unknown category (no derivation rule) ---
        _product(
            "misc_1",
            "Sunhouse quạt điều hòa",
            "Sunhouse",
            misc,
            "quat_dieu_hoa",
            {"capacity_btu": 5000},
        ),
    ]
    db.add_all(products)

    # --- legacy demo product: category_key is None (must never match a real key) ---
    db.add(
        Product(
            sku="demo_legacy",
            slug="demo-legacy",
            name="Legacy Demo Aircon Daikin",
            display_name="Legacy Demo Aircon Daikin",
            brand="Daikin",
            category=demo,
            category_key=None,
            short_description="x",
            image_url="x",
            specs_json=None,
        )
    )
    db.commit()


def _product(
    sku: str,
    name: str,
    brand: str,
    category: Category,
    category_key: str,
    specs_json: dict,
    *,
    sale_price: int | None = None,
) -> Product:
    product = Product(
        sku=sku,
        slug=sku.replace("_", "-"),
        name=name,
        display_name=name,
        brand=brand,
        category=category,
        category_key=category_key,
        short_description="x",
        image_url="x",
        specs_json=specs_json,
    )
    if sale_price is not None:
        product.price = Price(
            original_price=Decimal(sale_price),
            sale_price=Decimal(sale_price),
            currency="VND",
        )
    return product


def _skus(result: CatalogSearchResult) -> set[str]:
    return {p.sku for p in result.products}


# --------------------------------------------------------------------------- #
# Category isolation
# --------------------------------------------------------------------------- #
def test_category_filter_isolates(session: Session) -> None:
    ml = _skus(catalog_search(session, category_key="may_lanh"))
    assert ml == {"ml_priced_ok", "ml_priced_over", "ml_unpriced", "ml_small", "ml_btu_only"}

    tl = _skus(catalog_search(session, category_key="tu_lanh"))
    assert tl == {"tl_big", "tl_small", "tl_priced_over"}

    # No cross-contamination between categories.
    assert ml & tl == set()


def test_legacy_demo_product_never_matches_a_real_category(session: Session) -> None:
    for key in ("may_lanh", "tu_lanh", "quat_dieu_hoa"):
        assert "demo_legacy" not in _skus(catalog_search(session, category_key=key))


# --------------------------------------------------------------------------- #
# Budget filter (honesty guardrail: unpriced products are never budget-excluded)
# --------------------------------------------------------------------------- #
def test_budget_excludes_over_budget_priced_but_keeps_unpriced(session: Session) -> None:
    result = catalog_search(session, category_key="may_lanh", budget_max=12_000_000)
    skus = _skus(result)

    # Priced-and-within-headroom (10M <= 12.6M) stays.
    assert "ml_priced_ok" in skus
    # Priced-and-over-budget (25M) is excluded.
    assert "ml_priced_over" not in skus
    # Unpriced products are NOT excluded by a budget filter.
    assert {"ml_unpriced", "ml_small", "ml_btu_only"} <= skus
    assert result.total_count == 4


def test_budget_headroom_allows_five_percent_over(session: Session) -> None:
    # ml_priced_ok is 10M; a budget of 9.6M * 1.05 = 10.08M keeps it in.
    assert "ml_priced_ok" in _skus(
        catalog_search(session, category_key="may_lanh", budget_max=9_600_000)
    )
    # A budget of 9M * 1.05 = 9.45M pushes it out.
    assert "ml_priced_ok" not in _skus(
        catalog_search(session, category_key="may_lanh", budget_max=9_000_000)
    )


# --------------------------------------------------------------------------- #
# máy lạnh area-derived capacity filter
# --------------------------------------------------------------------------- #
def test_may_lanh_area_filter_excludes_too_small_capacity(session: Session) -> None:
    result = catalog_search(
        session, category_key="may_lanh", slots={"dien_tich_m2": 18}
    )
    skus = _skus(result)
    # In-range units stay.
    assert "ml_priced_ok" in skus  # area 15-20 covers 18
    assert "ml_priced_over" in skus  # area 18-30 covers 18
    # Too-small unit (area 8-13) is excluded.
    assert "ml_small" not in skus
    # BTU-fallback record (24000 BTU >= 18*600) stays.
    assert "ml_btu_only" in skus


def test_may_lanh_btu_fallback_and_direct_sun_multiplier(session: Session) -> None:
    # ml_btu_only has no area range -> BTU formula applies.
    # dien_tich 35 -> btu_can 21000 (no sun) <= 24000 -> included.
    assert "ml_btu_only" in _skus(
        catalog_search(session, category_key="may_lanh", slots={"dien_tich_m2": 35})
    )
    # With direct sun -> btu_can 35*600*1.3 = 27300 > 24000 -> excluded.
    assert "ml_btu_only" not in _skus(
        catalog_search(
            session,
            category_key="may_lanh",
            slots={"dien_tich_m2": 35, "nang_truc_tiep": True},
        )
    )


def test_direct_inverter_slot_filter(session: Session) -> None:
    # inverter maps through catalog_field_map (specs.inverter) for tủ lạnh.
    inv = _skus(catalog_search(session, category_key="tu_lanh", slots={"inverter": True}))
    assert inv == {"tl_big", "tl_priced_over"}
    assert "tl_small" not in inv


# --------------------------------------------------------------------------- #
# tủ lạnh people-derived capacity filter
# --------------------------------------------------------------------------- #
def test_tu_lanh_people_filter(session: Session) -> None:
    # so_nguoi_dung 5 -> lit_can = 45*5+100 = 325.
    result = catalog_search(session, category_key="tu_lanh", slots={"so_nguoi_dung": 5})
    skus = _skus(result)
    assert "tl_big" in skus  # 500 >= 325
    assert "tl_priced_over" in skus  # 600 >= 325
    assert "tl_small" not in skus  # 150 < 325


def test_tu_lanh_people_slot_accepts_string_value(session: Session) -> None:
    # so_nguoi_dung is a free-text slot; "5" must coerce to a number.
    skus = _skus(catalog_search(session, category_key="tu_lanh", slots={"so_nguoi_dung": "5"}))
    assert "tl_small" not in skus
    assert "tl_big" in skus


# --------------------------------------------------------------------------- #
# catalog_count parity
# --------------------------------------------------------------------------- #
def test_catalog_count_matches_search_when_limit_not_binding(session: Session) -> None:
    # No filters beyond category.
    assert catalog_count(session, category_key="may_lanh") == len(
        catalog_search(session, category_key="may_lanh", limit=100).products
    )
    # With budget + derivation slots.
    assert catalog_count(
        session, category_key="tu_lanh", budget_max=20_000_000, slots={"so_nguoi_dung": 5}
    ) == len(
        catalog_search(
            session,
            category_key="tu_lanh",
            budget_max=20_000_000,
            slots={"so_nguoi_dung": 5},
            limit=100,
        ).products
    )


# --------------------------------------------------------------------------- #
# pagination
# --------------------------------------------------------------------------- #
def test_limit_offset_pagination(session: Session) -> None:
    page1 = catalog_search(session, category_key="may_lanh", limit=2, offset=0)
    page2 = catalog_search(session, category_key="may_lanh", limit=2, offset=2)

    # total_count is the pre-limit count and stays constant across pages.
    assert page1.total_count == 5
    assert page2.total_count == 5
    assert len(page1.products) == 2
    assert len(page2.products) == 2
    # No overlap between consecutive pages.
    assert _skus(page1) & _skus(page2) == set()


# --------------------------------------------------------------------------- #
# fuzzy name lookup
# --------------------------------------------------------------------------- #
def test_name_query_finds_product_despite_typo(session: Session) -> None:
    # "daikn" is a typo of "Daikin" — difflib closeness should still match.
    result = catalog_search(session, category_key="may_lanh", name_query="daikn")
    assert "ml_priced_ok" in _skus(result)


def test_name_query_partial_substring_match(session: Session) -> None:
    result = catalog_search(session, category_key="may_lanh", name_query="FTKB35")
    assert _skus(result) == {"ml_priced_ok"}


def test_name_query_respects_category_filter(session: Session) -> None:
    # A Daikin-named legacy demo exists but is category_key=None, so a máy_lanh
    # name search must not surface it.
    assert "demo_legacy" not in _skus(
        catalog_search(session, category_key="may_lanh", name_query="daikin")
    )


# --------------------------------------------------------------------------- #
# unknown category (no derivation rule) — must not crash
# --------------------------------------------------------------------------- #
def test_unknown_category_skips_capacity_filter_without_crashing(session: Session) -> None:
    # No derivation rule for quat_dieu_hoa — capacity-style slots are ignored,
    # the product is still returned, nothing raises.
    result = catalog_search(
        session, category_key="quat_dieu_hoa", slots={"dien_tich_m2": 18, "so_nguoi_dung": 4}
    )
    assert _skus(result) == {"misc_1"}


# --------------------------------------------------------------------------- #
# schema shape
# --------------------------------------------------------------------------- #
def test_tool_schema_shape() -> None:
    assert TOOL_SCHEMA["name"] == "catalog_search"
    assert "description" in TOOL_SCHEMA
    input_schema = TOOL_SCHEMA["input_schema"]
    assert input_schema["type"] == "object"
    assert "category_key" in input_schema["properties"]
    assert input_schema["required"] == ["category_key"]
