"""price_promo_stock tool tests (task 11) — provenance-wrapped facts JSON,
honesty guardrail for missing price/stock data.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.core.config import Settings
from src.tools.price_promo_stock import PricePromoStockTool

FIXED_NOW = datetime(2026, 7, 18, 9, 12, 0, tzinfo=UTC)


@pytest.fixture()
def fixture_dir(tmp_path: Path) -> Path:
    category = [
        {
            "sku": "SKU-PRICED-1",
            "category_key": "may_lanh",
            "original_price": 11_490_000,
            "sale_price": 10_990_000,
            "has_price_data": True,
            "promotions": ["Miễn phí công lắp đặt"],
        },
        {
            "sku": "SKU-NOPRICE-1",
            "category_key": "may_lanh",
            "original_price": None,
            "sale_price": None,
            "has_price_data": False,
            "promotions": [],
        },
    ]
    (tmp_path / "may_lanh.json").write_text(json.dumps(category), encoding="utf-8")
    # Non-category summary files must be skipped, not treated as a category.
    (tmp_path / "_summary.json").write_text(json.dumps({"not": "a category"}), encoding="utf-8")
    return tmp_path


@pytest.fixture()
def tool(fixture_dir: Path) -> PricePromoStockTool:
    settings = Settings(realdata_processed_path=str(fixture_dir))
    return PricePromoStockTool(settings=settings, clock=lambda: FIXED_NOW)


def test_facts_have_provenance_shape(tool: PricePromoStockTool) -> None:
    facts = tool.get_facts("SKU-PRICED-1")
    assert facts is not None
    data = facts.to_dict()

    assert data["sale_price"] == {
        "value": 10_990_000,
        "source": {"dataset": "may_lanh", "row": "SKU-PRICED-1", "field": "sale_price"},
        "fetched_at": FIXED_NOW.isoformat(),
    }


def test_missing_price_data_is_null_not_fabricated(tool: PricePromoStockTool) -> None:
    facts = tool.get_facts("SKU-NOPRICE-1")
    assert facts is not None
    assert facts.original_price.value is None
    assert facts.sale_price.value is None
    assert facts.promotions.value == []


def test_stock_is_always_null_no_inventory_data_exists(tool: PricePromoStockTool) -> None:
    facts = tool.get_facts("SKU-PRICED-1")
    assert facts is not None
    assert facts.stock.value is None
    assert facts.stock.source["dataset"] == "unavailable"


def test_unknown_sku_returns_none(tool: PricePromoStockTool) -> None:
    assert tool.get_facts("does-not-exist") is None


def test_summary_file_is_not_indexed_as_a_category(tool: PricePromoStockTool) -> None:
    assert tool.get_facts("not") is None


@pytest.mark.anyio
async def test_get_facts_many_fans_out_over_skus(tool: PricePromoStockTool) -> None:
    results = await tool.get_facts_many(["SKU-PRICED-1", "SKU-NOPRICE-1", "missing"])
    assert results["SKU-PRICED-1"] is not None
    assert results["SKU-NOPRICE-1"] is not None
    assert results["missing"] is None


class TestAgainstRealDataset:
    """Smoke tests against the actual data/realdata/processed export (not a
    fixture) to prove the adapter reads the real ETL output correctly.
    """

    def test_real_priced_sku_from_may_lanh(self) -> None:
        tool = PricePromoStockTool(Settings())
        facts = tool.get_facts("1751098000210")
        assert facts is not None
        assert facts.original_price.value == 29_490_000
        assert facts.sale_price.value == 29_490_000
        assert facts.original_price.source["dataset"] == "may_lanh"
        assert len(facts.promotions.value) == 8

    def test_real_unpriced_sku_from_may_lanh(self) -> None:
        tool = PricePromoStockTool(Settings())
        facts = tool.get_facts("3051098001617")
        assert facts is not None
        assert facts.original_price.value is None
        assert facts.sale_price.value is None
