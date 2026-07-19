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
