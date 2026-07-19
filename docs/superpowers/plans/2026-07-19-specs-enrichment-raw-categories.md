# Specs Enrichment for Raw Categories — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the chat's `Product.specs_json` parsed numeric/boolean fields for the 9 `specs_raw`-only categories by reusing the existing importer parser, then declare `ranking_criteria` so the advisory spine produces real trade-offs/benefits for them.

**Architecture:** A new seed step (`src/seed/enrich_specs.py`) runs the existing `normalize_product_row` (from `src/importers/`) over the clean CSVs, coerces `Decimal`→int/float, and merges the flat typed values into each product's `specs_json` by `sku`. No new parser, no schema change, no touch to the 5 already-parsed categories. `ranking_criteria` + GLOSSARY/field_label entries make the fields rank and render.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, pandas (via `read_csv`), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-19-specs-enrichment-raw-categories-design.md`.
- Predecessor spine already merged on this branch (S5 reads `ranking_criteria`, direction semantics `higher_better`/`lower_better`/`boolean_pref`/`target`).
- Working dir for commands: `/home/tuanjhg/Work/VAIC/apps/api`. Tests: `.venv/bin/python -m pytest`. Lint: `.venv/bin/ruff check src tests`. Types: `.venv/bin/mypy src`.
- **`ranking_criteria` must reference `specs.<key>` (parsed), never `specs_raw.*`.** No `target` for these 9 (no reliable need formula).
- **Never write `Decimal` into `specs_json`** — S5's `_numeric` rejects `Decimal`. Coerce via `csv_importer._json_value`.
- Only enrich the 9 raw categories; leave the 5 parsed ones untouched.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Finalized `ranking_criteria` (verified against real CSV coverage)

| category_key | registry code | csv | criteria (field → direction) |
|---|---|---|---|
| pc_de_ban | desktop_computers | pc_de_ban.csv | ram_gb↑, storage_gb↑, cpu_base_clock_ghz↑ |
| may_tinh_bang | tablets | may_tinh_bang.csv | ram_gb↑, storage_gb↑, battery_capacity_mah↑, cpu_speed_ghz↑ |
| man_hinh | computer_monitors | man_hinh.csv | resolution_width↑, response_time_ms↓, brightness_nit↑ |
| may_in | printers | may_in.csv | print_resolution_dpi↑, monthly_duty_cycle↑, print_speed_ppm↑ |
| may_say | clothes_dryers | may_say.csv | energy_consumption_kwh↓, drying_capacity_kg↑ |
| may_nuoc_nong | water_heaters | may_nuoc_nong.csv | has_booster_pump (boolean_pref), power_watt↑ |
| tu_mat_dong | coolers_freezers | tu_mat_dong.csv | inverter (boolean_pref), energy_consumption_kwh↓ |
| micro_thu_am | phone_recording_microphones | micro_thu_am.csv | transmission_distance_meter↑ |
| micro_karaoke | karaoke_microphones | micro_karaoke.csv | distortion_percent↓ |

---

## File Structure

- `src/seed/enrich_specs.py` — new: category map, `parsed_numeric_specs`, `enrich_specs`, `main`. (Tasks 1, 2)
- `src/pipeline/slots/<9 categories>.yaml` — add `ranking_criteria`. (Task 3)
- `src/pipeline/s6_generate.py` — GLOSSARY renderers for new fields. (Task 4)
- `src/pipeline/s8_respond.py` — `_FIELD_LABELS` for new fields. (Task 4)
- `Makefile`, `deploy/docker-compose.prod.yml` — add enrich step to seed chain. (Task 2)
- Tests: `tests/test_enrich_specs.py` (new), `tests/test_slots.py`, `tests/test_s6_generate.py`, `tests/test_s5_ranking.py`, `tests/test_chat_advisor.py`.

---

## Task 1: `parsed_numeric_specs` — reuse the parser, coerce to plain numbers

**Files:**
- Create: `src/seed/enrich_specs.py`
- Test: `tests/test_enrich_specs.py`

**Interfaces:**
- Produces:
  - `_RAW_CATEGORIES: dict[str, tuple[str, str]]` — chat `category_key` → (`registry_code`, `csv_filename`).
  - `parsed_numeric_specs(row: dict[str, Any], config: CategoryConfig) -> dict[str, int | float | bool]`
    — flat parsed numeric/boolean typed values only, `Decimal` coerced, empties dropped.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enrich_specs.py`:

```python
from decimal import Decimal

from src.importers.category_registry import CATEGORY_REGISTRY
from src.seed.enrich_specs import _RAW_CATEGORIES, parsed_numeric_specs


def test_all_nine_raw_categories_are_mapped():
    assert set(_RAW_CATEGORIES) == {
        "tu_mat_dong", "man_hinh", "may_in", "may_nuoc_nong", "may_say",
        "may_tinh_bang", "micro_karaoke", "micro_thu_am", "pc_de_ban",
    }


def test_parsed_numeric_specs_coerces_decimal_and_drops_empty():
    config = CATEGORY_REGISTRY["desktop_computers"]
    row = {"ram": "16GB", "o_cung": "512GB SSD", "toc_do_cpu": "1.3 GHz", "so_nhan": "Không có"}
    out = parsed_numeric_specs(row, config)
    assert out["ram_gb"] == 16 and isinstance(out["ram_gb"], int)
    assert out["storage_gb"] == 512
    assert isinstance(out["cpu_base_clock_ghz"], float)
    assert not any(isinstance(v, Decimal) for v in out.values())
    assert "cpu_core_count" not in out  # "Không có" dropped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_enrich_specs.py -v`
Expected: FAIL (`ModuleNotFoundError: src.seed.enrich_specs`).

- [ ] **Step 3: Create the module + helper**

Create `src/seed/enrich_specs.py`:

```python
"""Enrich Product.specs_json for the 9 specs_raw-only categories by reusing the
importer parser (src/importers), so the advisory spine (S5 ranking_criteria) has
real numeric/boolean fields to rank on. No new parser, no schema change; only the
chat's specs_json column is touched, and only for these 9 categories.
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

    Reuses the importer's ``normalize_product_row`` (which applies the registry's
    per-column parsers and drops empties/"Không có"), keeps only number/boolean
    attributes, and coerces ``Decimal`` -> int/float via ``_json_value`` so S5's
    ``_numeric`` accepts the value.
    """
    normalized = normalize_product_row(row, config)
    out: dict[str, Any] = {}
    for key, (attribute, parsed, _raw) in normalized.typed_values.items():
        if attribute.data_type in ("number", "boolean"):
            out[key] = _json_value(parsed)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_enrich_specs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/seed/enrich_specs.py tests/test_enrich_specs.py
git commit -m "feat(enrich): reuse importer parser to coerce raw specs to numbers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `enrich_specs` orchestration + DB merge + seed wiring

**Files:**
- Modify: `src/seed/enrich_specs.py` (add `enrich_specs`, `main`)
- Modify: `Makefile` (seed target), `deploy/docker-compose.prod.yml` (seed command)
- Test: `tests/test_enrich_specs.py`

**Interfaces:**
- Consumes: `parsed_numeric_specs`, `_RAW_CATEGORIES` (Task 1).
- Produces: `enrich_specs(db: Session, clean_csv_dir: Path) -> dict[str, dict[str, int]]`
  (report: per category_key `{"rows", "matched", "enriched"}`). Merges parsed keys into
  `Product.specs_json` by `sku`, reassigning the dict so SQLAlchemy detects the change.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_enrich_specs.py`:

```python
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.models import Category, Product
from src.seed.enrich_specs import enrich_specs


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        cat = Category(code="pc_de_ban", name="PC", slug="pc")
        session.add(cat)
        session.flush()
        session.add(Product(
            sku="S1", slug="s1", name="PC S1", display_name="PC S1", brand="X",
            category_id=cat.id, category_key="pc_de_ban", specs_json={"display_name": "PC S1"},
        ))
        session.commit()
        yield session


def test_enrich_merges_parsed_specs_by_sku(db: Session, tmp_path: Path):
    csv = tmp_path / "pc_de_ban.csv"
    csv.write_text("sku,ram,o cung,toc do cpu\nS1,16GB,512GB SSD,1.3 GHz\n", encoding="utf-8")

    report = enrich_specs(db, tmp_path)

    product = db.query(Product).filter_by(sku="S1").one()
    assert product.specs_json["ram_gb"] == 16
    assert product.specs_json["storage_gb"] == 512
    assert product.specs_json["display_name"] == "PC S1"  # preserved
    assert report["pc_de_ban"]["enriched"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_enrich_specs.py::test_enrich_merges_parsed_specs_by_sku -v`
Expected: FAIL (`enrich_specs` not defined).

- [ ] **Step 3: Implement `enrich_specs` + `main`**

Append to `src/seed/enrich_specs.py`:

```python
def enrich_specs(db: Session, clean_csv_dir: Path) -> dict[str, dict[str, int]]:
    """Merge parsed numeric/boolean specs into Product.specs_json for the 9 raw
    categories, matched by sku. Idempotent (re-running overwrites parsed keys).
    Returns a per-category coverage report."""
    report: dict[str, dict[str, int]] = {}
    for category_key, (code, filename) in _RAW_CATEGORIES.items():
        config = CATEGORY_REGISTRY[code]
        path = clean_csv_dir / filename
        if not path.exists():
            report[category_key] = {"rows": 0, "matched": 0, "enriched": 0}
            continue
        frame = read_csv(path)
        by_sku: dict[str, dict[str, Any]] = {}
        for record in frame.to_dict("records"):
            sku = record.get("sku")
            if sku is None:
                continue
            parsed = parsed_numeric_specs(record, config)
            if parsed:
                by_sku[str(sku)] = parsed

        matched = 0
        products = db.scalars(
            select(Product).where(Product.category_key == category_key)
        ).all()
        for product in products:
            parsed = by_sku.get(str(product.sku))
            if not parsed:
                continue
            merged = dict(product.specs_json or {})
            merged.update(parsed)
            product.specs_json = merged  # reassign so SQLAlchemy detects the change
            matched += 1
        db.flush()
        report[category_key] = {"rows": len(frame), "matched": matched, "enriched": matched}
    db.commit()
    return report


def main() -> None:
    from src.core.config import settings
    from src.core.database import SessionLocal

    clean_dir = Path(settings.realdata_processed_path).resolve().parent / "raw" / "clean"
    with SessionLocal() as db:
        report = enrich_specs(db, clean_dir)
    for category_key, stats in report.items():
        print(f"{category_key}: {stats}")


if __name__ == "__main__":
    main()
```

Note: confirm the session factory name by mirroring `src/seed/seed_realdata.py`'s `main()`
(use whatever it imports — `SessionLocal` or a `session_scope`). Match it exactly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_enrich_specs.py -v`
Expected: PASS.

- [ ] **Step 5: Wire into the seed chain**

In `Makefile`, in the seed target, add a line after `seed_realdata`:

```makefile
	docker compose run --rm api python -m src.seed.enrich_specs
```

In `deploy/docker-compose.prod.yml`, in the `command:` string, insert `&& python -m src.seed.enrich_specs` immediately after `python -m src.seed.seed_realdata`.

- [ ] **Step 6: Commit**

```bash
git add src/seed/enrich_specs.py tests/test_enrich_specs.py Makefile deploy/docker-compose.prod.yml
git commit -m "feat(enrich): merge parsed specs into specs_json + wire into seed chain

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `ranking_criteria` for the 9 categories

**Files:**
- Modify: the 9 `src/pipeline/slots/<category>.yaml`
- Test: `tests/test_slots.py`

**Interfaces:**
- Consumes: `SlotProfile.ranking_criteria` (already in the schema from the spine work).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_slots.py`:

```python
RAW_CATEGORIES_WITH_CRITERIA = [
    "pc_de_ban", "may_tinh_bang", "man_hinh", "may_in", "may_say",
    "may_nuoc_nong", "tu_mat_dong", "micro_thu_am", "micro_karaoke",
]


@pytest.mark.parametrize("category_key", RAW_CATEGORIES_WITH_CRITERIA)
def test_raw_category_declares_specs_ranking_criteria(category_key: str) -> None:
    profile = load_slot_profile(category_key)
    assert profile.ranking_criteria, f"{category_key} has no ranking_criteria"
    for criterion in profile.ranking_criteria:
        assert criterion.direction in {"higher_better", "lower_better", "boolean_pref"}
        # criteria reference parsed specs keys, never the raw label paths
        assert " " not in criterion.field and "." not in criterion.field
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_slots.py -k raw_category_declares -v`
Expected: FAIL (empty `ranking_criteria`).

- [ ] **Step 3: Add each `ranking_criteria` block**

Append to each YAML (values from the finalized table above). Example — `pc_de_ban.yaml`:

```yaml
ranking_criteria:
  - field: ram_gb
    direction: higher_better
  - field: storage_gb
    direction: higher_better
  - field: cpu_base_clock_ghz
    direction: higher_better
```

`may_tinh_bang.yaml`:

```yaml
ranking_criteria:
  - field: ram_gb
    direction: higher_better
  - field: storage_gb
    direction: higher_better
  - field: battery_capacity_mah
    direction: higher_better
  - field: cpu_speed_ghz
    direction: higher_better
```

`man_hinh.yaml`:

```yaml
ranking_criteria:
  - field: resolution_width
    direction: higher_better
  - field: response_time_ms
    direction: lower_better
  - field: brightness_nit
    direction: higher_better
```

`may_in.yaml`:

```yaml
ranking_criteria:
  - field: print_resolution_dpi
    direction: higher_better
  - field: monthly_duty_cycle
    direction: higher_better
  - field: print_speed_ppm
    direction: higher_better
```

`may_say.yaml`:

```yaml
ranking_criteria:
  - field: energy_consumption_kwh
    direction: lower_better
  - field: drying_capacity_kg
    direction: higher_better
```

`may_nuoc_nong.yaml`:

```yaml
ranking_criteria:
  - field: has_booster_pump
    direction: boolean_pref
  - field: power_watt
    direction: higher_better
```

`tu_mat_dong.yaml`:

```yaml
ranking_criteria:
  - field: inverter
    direction: boolean_pref
  - field: energy_consumption_kwh
    direction: lower_better
```

`micro_thu_am.yaml`:

```yaml
ranking_criteria:
  - field: transmission_distance_meter
    direction: higher_better
```

`micro_karaoke.yaml`:

```yaml
ranking_criteria:
  - field: distortion_percent
    direction: lower_better
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_slots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/slots/*.yaml tests/test_slots.py
git commit -m "feat(slots): ranking_criteria for the 9 raw categories

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: GLOSSARY + field labels for the new fields

**Files:**
- Modify: `src/pipeline/s6_generate.py` (`GLOSSARY`, `_FIELD_LABELS`)
- Modify: `src/pipeline/s8_respond.py` (`_FIELD_LABELS`)
- Test: `tests/test_s6_generate.py`

**Interfaces:**
- Consumes: `render_spec` (existing). Produces glossary phrases for every field used in Task 3's criteria.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_s6_generate.py`:

```python
import pytest

from src.pipeline.s6_generate import render_spec


@pytest.mark.parametrize("field,value,needle", [
    ("ram_gb", 16, "RAM 16GB"),
    ("storage_gb", 512, "512GB"),
    ("resolution_width", 1920, "1920"),
    ("response_time_ms", 1, "1ms"),
    ("brightness_nit", 300, "300"),
    ("print_speed_ppm", 20, "20 trang/phút"),
    ("energy_consumption_kwh", 1.5, "1.5"),
    ("drying_capacity_kg", 9, "9kg"),
    ("distortion_percent", 0.5, "0.5%"),
])
def test_new_glossary_fields_render(field, value, needle):
    rendered = render_spec(field, value)
    assert rendered is not None and needle in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_s6_generate.py -k new_glossary_fields -v`
Expected: FAIL (renderers absent → `render_spec` returns None).

- [ ] **Step 3: Add GLOSSARY renderers**

In `src/pipeline/s6_generate.py`, add these entries into the `GLOSSARY` dict (alongside the existing ones):

```python
    # pc / tablet
    "ram_gb": lambda v: f"RAM {v}GB",
    "storage_gb": lambda v: f"bộ nhớ lưu trữ {v}GB",
    "cpu_base_clock_ghz": lambda v: f"xung nhịp CPU {v}GHz",
    "cpu_speed_ghz": lambda v: f"tốc độ CPU {v}GHz",
    "battery_capacity_mah": lambda v: f"pin {v}mAh",
    # màn hình
    "resolution_width": lambda v: f"độ phân giải ngang {v}px",
    "response_time_ms": lambda v: f"thời gian đáp ứng {v}ms",
    "brightness_nit": lambda v: f"độ sáng {v} nit",
    # máy in
    "print_resolution_dpi": lambda v: f"độ phân giải in {v}dpi",
    "monthly_duty_cycle": lambda v: f"công suất in {v} trang/tháng",
    "print_speed_ppm": lambda v: f"tốc độ in {v} trang/phút",
    # máy sấy / tủ mát / máy nước nóng
    "energy_consumption_kwh": lambda v: f"điện năng tiêu thụ {v}kWh",
    "drying_capacity_kg": lambda v: f"sấy được {v}kg mỗi mẻ",
    "has_booster_pump": lambda v: "có bơm trợ lực tăng áp" if v else "không có bơm trợ lực",
    # micro
    "transmission_distance_meter": lambda v: f"khoảng cách truyền {v}m",
    "distortion_percent": lambda v: f"độ méo tiếng {v}%",
```

Also add the same field → short label mapping to the `_FIELD_LABELS` dict in **both**
`src/pipeline/s6_generate.py` and `src/pipeline/s8_respond.py`:

```python
    "ram_gb": "RAM",
    "storage_gb": "bộ nhớ lưu trữ",
    "cpu_base_clock_ghz": "xung nhịp CPU",
    "cpu_speed_ghz": "tốc độ CPU",
    "battery_capacity_mah": "dung lượng pin",
    "resolution_width": "độ phân giải",
    "response_time_ms": "thời gian đáp ứng",
    "brightness_nit": "độ sáng",
    "print_resolution_dpi": "độ phân giải in",
    "monthly_duty_cycle": "công suất in",
    "print_speed_ppm": "tốc độ in",
    "energy_consumption_kwh": "điện năng tiêu thụ",
    "drying_capacity_kg": "khối lượng sấy",
    "has_booster_pump": "bơm trợ lực",
    "transmission_distance_meter": "khoảng cách truyền",
    "distortion_percent": "độ méo tiếng",
    "power_watt": "công suất điện",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s6_generate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/s6_generate.py src/pipeline/s8_respond.py tests/test_s6_generate.py
git commit -m "feat(s6): glossary + labels for enriched-category fields

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: S5 ranking behaves for an enriched category (pc_de_ban)

**Files:**
- Test: `tests/test_s5_ranking.py` (no source change — proves the spine works with the new criteria)

**Interfaces:**
- Consumes: `rank_candidates`, `load_slot_profile("pc_de_ban")`.

- [ ] **Step 1: Write the test**

Add to `tests/test_s5_ranking.py`:

```python
PC_PROFILE: SlotProfile = load_slot_profile("pc_de_ban")


def _pc_cand(sku, *, price=15_000_000, **specs):
    return {"sku": sku, "name": f"PC {sku}", "specs": dict(specs), "price": price, "in_stock": None}


def test_pc_de_ban_higher_ram_ranks_first() -> None:
    cands = [
        _pc_cand("AAA_LOW", ram_gb=8, storage_gb=256, cpu_base_clock_ghz=2.0),
        _pc_cand("ZZZ_HIGH", ram_gb=32, storage_gb=256, cpu_base_clock_ghz=2.0),
    ]
    result = rank_candidates(cands, NeedProfile(category="pc_de_ban", slots={}), PC_PROFILE)
    assert result.top[0].sku == "ZZZ_HIGH"  # only real scoring beats the sku tie-break


def test_pc_de_ban_ram_vs_storage_is_a_tradeoff() -> None:
    cands = [
        _pc_cand("A", ram_gb=32, storage_gb=256, cpu_base_clock_ghz=2.0),
        _pc_cand("B", ram_gb=8, storage_gb=1024, cpu_base_clock_ghz=2.0),
    ]
    result = rank_candidates(cands, NeedProfile(category="pc_de_ban", slots={}), PC_PROFILE)
    fields = {f for t in result.trade_offs for f in (t.a_wins_on + t.b_wins_on)}
    assert {"ram_gb", "storage_gb"} & fields
```

- [ ] **Step 2: Run it (should pass on the existing spine)**

Run: `.venv/bin/python -m pytest tests/test_s5_ranking.py -k pc_de_ban -v`
Expected: PASS (S5 already reads `ranking_criteria`; Task 3 added pc_de_ban's). If FAIL, confirm Task 3's pc_de_ban block and field names match the criteria.

- [ ] **Step 3: Commit**

```bash
git add tests/test_s5_ranking.py
git commit -m "test(s5): pc_de_ban ranks on enriched specs criteria

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: End-to-end enriched category (pc_de_ban) advisory turn

**Files:**
- Test: `tests/test_chat_advisor.py`

**Interfaces:**
- Consumes: `AdvisorChatService` with the file's existing fakes (`QueuedRouter`, `_s2`, `FakeFactsTool`).

- [ ] **Step 1: Write the test**

Add to `tests/test_chat_advisor.py`, mirroring the existing `tu_lanh_db` fixture pattern — a `pc_db` fixture seeding a `pc_de_ban` category with two products whose `specs_json` already carries enriched keys (simulating post-enrich state):

```python
@pytest.fixture()
def pc_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as session:
        category = Category(code="pc_de_ban", name="PC", slug="pc")
        session.add(category); session.flush()
        rows = [
            ("pc_hi", "Dell mạnh", {"ram_gb": 32, "storage_gb": 512, "cpu_base_clock_ghz": 3.0}),
            ("pc_lo", "Acer phổ thông", {"ram_gb": 8, "storage_gb": 256, "cpu_base_clock_ghz": 2.0}),
        ]
        for sku, name, spec in rows:
            session.add(Product(
                sku=sku, slug=sku, name=name, display_name=name, brand=name.split()[0],
                category_id=category.id, category_key="pc_de_ban", specs_json=spec,
                short_description=name, image_url=f"https://img.example/{sku}.jpg",
            ))
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


def test_pc_de_ban_enriched_cards_are_differentiated(pc_db: Session) -> None:
    router = QueuedRouter(_s2(category="pc_de_ban", slots={}), "[1] cấu hình mạnh.")
    profile = NeedProfile(category="pc_de_ban", slots={"ngan_sach_max": 20_000_000})
    response = asyncio.run(_service(pc_db, router).reply(_request("cần PC văn phòng", profile)))

    assert response.response_type == "recommendations"
    assert response.cards[0].sku == "pc_hi"  # stronger config ranks first
    # benefit + trade-off are real, not the "chưa đủ dữ liệu" fallback
    assert "chưa đủ dữ liệu" not in response.cards[0].trade_off.lower()
    assert response.cards[0].reason != (
        "Phù hợp với nhu cầu đã nêu dựa trên thông tin sản phẩm hiện có."
    )
    assert any("RAM" in s or "GB" in s for s in response.cards[0].strengths)
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_chat_advisor.py::test_pc_de_ban_enriched_cards_are_differentiated -v`
Expected: PASS (spine + Task 3/4 render). If the card ordering fails, verify the pc_de_ban criteria/glossary names.

- [ ] **Step 3: Commit**

```bash
git add tests/test_chat_advisor.py
git commit -m "test(advisor): end-to-end differentiated cards for enriched pc_de_ban

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Run enrich for real + coverage + full regression

**Files:** none (verification + report).

- [ ] **Step 1: Run enrich against a real seeded dev DB**

If a local dev DB is seeded, run: `.venv/bin/python -m src.seed.enrich_specs`
Expected: prints a per-category report; note the `enriched` counts (e.g. pc_de_ban ~377+, man_hinh ~420+). Record them.

If no dev DB is available, run the coverage dry-run instead (no DB) and record per-category counts:

```bash
.venv/bin/python -c "
from pathlib import Path
from collections import Counter
from src.importers.csv_importer import read_csv, normalize_product_row
from src.importers.category_registry import CATEGORY_REGISTRY
from src.seed.enrich_specs import _RAW_CATEGORIES, parsed_numeric_specs
for ck,(code,f) in _RAW_CATEGORIES.items():
    df=read_csv(Path('../../data/realdata/raw/clean/'+f)); c=CATEGORY_REGISTRY[code]
    n=sum(1 for r in df.to_dict('records') if parsed_numeric_specs(r,c))
    print(f'{ck}: {n}/{len(df)} rows enrichable')
"
```

- [ ] **Step 2: Full suite + lint + types**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (no regression in the 5 already-parsed categories).
Run: `.venv/bin/ruff check src tests && .venv/bin/mypy src`
Expected: clean. (If `_json_value` import trips a private-name lint rule, add a thin public re-export or a local alias — do not silence with noqa blindly.)

- [ ] **Step 3: Verify one raw category by hand**

Drive a `pc_de_ban` (or `man_hinh`) advisory turn through the service (as in Task 6, or a small script) and confirm the cards show differentiated, plain-language benefits/trade-offs from the enriched fields — not "chưa đủ dữ liệu".

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(enrich): coverage report + regression sweep for raw-category enrichment

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §3.1 enrich step → Tasks 1, 2. ✓
- §3.2 ranking_criteria (9 categories, verified fields) → Task 3. ✓
- §3.3 GLOSSARY + field_label → Task 4. ✓
- §3.4 no S5/S2/S4 change → Tasks 5, 6 prove behavior with no source change. ✓
- §4 tests (enrich, s5, slots, render, e2e, coverage) → Tasks 1–7. ✓
- §5 risks (Decimal coercion, sku match report, sparsity, direction sanity) → Task 1 (coercion test), Task 2 (report), Task 7 (coverage), Task 3 (verified fields). ✓

**Type consistency:** `parsed_numeric_specs(row, config) -> dict`, `enrich_specs(db, clean_csv_dir) -> report`, `_RAW_CATEGORIES` shape, and the criteria field names are used identically across Tasks 1–6. Glossary keys match the criteria field names exactly.

**Placeholder scan:** every step has concrete code/commands. One flagged confirmation: Task 2 Step 3 says to match `seed_realdata.py`'s actual session factory name — an instruction to verify against the file, not a placeholder value.
