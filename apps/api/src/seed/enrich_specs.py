"""Enrich Product.specs_json for the 9 specs_raw-only categories by reusing the
importer parser (src/importers), so the advisory spine (S5 ranking_criteria) has
real numeric/boolean fields to rank on.

No new parser, no schema change: only the chat's ``specs_json`` column is touched,
and only for these 9 categories. The 5 already-parsed categories (máy lạnh, tủ
lạnh + the 3 uu_tien ones) are left alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.importers.category_registry import CATEGORY_REGISTRY, CategoryConfig
from src.importers.csv_importer import _json_value, normalize_product_row, read_csv
from src.models import Product

# chat category_key -> (importer registry code, clean CSV filename)
_RAW_CATEGORIES: dict[str, tuple[str, str]] = {
    "tu_mat_dong": ("coolers_freezers", "tu_mat_dong.csv"),
    "man_hinh": ("computer_monitors", "man_hinh.csv"),
    "may_in": ("printers", "may_in.csv"),
    "may_nuoc_nong": ("water_heaters", "may_nuoc_nong.csv"),
    "may_say": ("clothes_dryers", "may_say.csv"),
    "may_tinh_bang": ("tablets", "may_tinh_bang.csv"),
    "micro_karaoke": ("karaoke_microphones", "micro_karaoke.csv"),
    "micro_thu_am": ("phone_recording_microphones", "micro_thu_am.csv"),
    "pc_de_ban": ("desktop_computers", "pc_de_ban.csv"),
}


def parsed_numeric_specs(row: dict[str, Any], config: CategoryConfig) -> dict[str, Any]:
    """Flat ``{key: int|float|bool}`` for numeric/boolean typed attributes only.

    Reuses the importer's :func:`normalize_product_row` (which applies the
    registry's per-column parsers and drops empties/"Không có"), keeps only
    number/boolean attributes, and coerces ``Decimal`` → int/float via
    :func:`_json_value` so S5's ``_numeric`` accepts the value.
    """
    normalized = normalize_product_row(row, config)
    out: dict[str, Any] = {}
    for key, (attribute, parsed, _raw) in normalized.typed_values.items():
        if attribute.data_type in ("number", "boolean"):
            out[key] = _json_value(parsed)
    return out
