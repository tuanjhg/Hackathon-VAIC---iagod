"""Slot YAML v0 loader (task 5).

Category-specific required/optional slot definitions, hand-authored as the
Phase 0 bootstrap/fallback per `docs/research/dmx-ai-workflow-v1.md` §2:
"YAML v0 viết tay (từ brief H2 + facets DMX) vẫn làm ở Phase 0 làm nền chạy
ngay + làm fallback; compiler v0 build ở Phase 3 chạy lại trên 4 ngành để so
với bản tay (chính là validation)". The Category Profile Compiler (ADR A7,
ngành hàng slot logic sinh từ catalog + guide corpus + expert review) is
separate, later work — this package is the "bản tay" it will be compared
against, not a replacement for it.

Each YAML file's ``category_key`` matches the category_key values in
`data/realdata/processed/*.json`.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

_SLOTS_DIR = Path(__file__).parent

SlotType = Literal[
    "money",
    "integer",
    "area_m2",
    "volume_liter",
    "power_watt",
    "enum",
    "multi_enum",
    "boolean",
    "text",
]


class SlotDef(BaseModel):
    name: str
    label: str
    type: SlotType
    sample_question: str
    catalog_field: str | list[str] | None = None
    values: list[str] | None = None
    priority_rank: int | None = None
    rationale: str | None = None


class DerivationRule(BaseModel):
    name: str
    description: str


class SlotProfile(BaseModel):
    category_key: str
    category_label: str
    source_notes: str
    required_slots: list[SlotDef]
    optional_slots: list[SlotDef]
    derivation_rules: list[DerivationRule] = []
    catalog_field_map: dict[str, str] = {}
    data_quality: str = ""


def available_categories() -> list[str]:
    """category_key values with a slot profile on disk, sorted."""
    return sorted(path.stem for path in _SLOTS_DIR.glob("*.yaml"))


def load_slot_profile(category_key: str) -> SlotProfile:
    path = _SLOTS_DIR / f"{category_key}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No slot profile for category '{category_key}'")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SlotProfile.model_validate(data)
