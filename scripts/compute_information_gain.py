"""Offline information-gain precompute for optional slots (STT19).

For each product category that has a hand-authored slot profile
(``apps/api/src/pipeline/slots/*.yaml``), read the real catalog
``data/realdata/processed/<category_key>.json`` and, for every OPTIONAL slot,
compute a Shannon-entropy-based information-gain score from the catalog
field(s) that slot depends on.

The idea: a slot whose backing catalog field varies a lot across the category
(high entropy) discriminates products strongly, so asking about it yields more
information than asking about a field that is nearly constant (low entropy).
This produces a *data-driven* companion to the hand-authored ``priority_rank``
in the YAML. Wiring the result back into the S3 dialogue policy
(``apps/api/src/pipeline/s3_policy.py``) as a ranking override is deliberately
out of scope — this script only produces the artifact.

Bucketing
---------
* Continuous numeric fields (typed ``int``/``float``, ``bool`` excluded, more
  than 4 distinct values) are bucketed into quartiles ``Q1..Q4``.
* Everything else (booleans, strings, low-cardinality numerics, mixed types) is
  treated categorically: each distinct value is its own bucket.
* Missing / ``null`` values always form their own bucket (:data:`MISSING_BUCKET`).

For a slot backed by several fields, the per-field entropies are averaged so
multi-field slots are not inflated merely by having more fields.

Output
------
``apps/api/src/pipeline/profiles/information_gain/<category_key>.json`` with the
per-slot scores keyed by slot name, a ``ranked_slots`` list sorted by entropy
descending, and an ``_meta`` block. A human-readable table is printed to stdout.

Run manually::

    apps/api/.venv/bin/python scripts/compute_information_gain.py
    apps/api/.venv/bin/python scripts/compute_information_gain.py may_lanh tu_lanh
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_API_DIR = _REPO_ROOT / "apps" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from src.pipeline.slots import (  # noqa: E402
    SlotDef,
    SlotProfile,
    available_categories,
    load_slot_profile,
)

MISSING_BUCKET = "__missing__"
"""Bucket label for missing / null field values."""

_MIN_DISTINCT_FOR_QUARTILES = 5
"""A numeric field needs more than 4 distinct values to be quartile-bucketed."""

_CATALOG_DIR = _REPO_ROOT / "data" / "realdata" / "processed"
_OUTPUT_DIR = _API_DIR / "src" / "pipeline" / "profiles" / "information_gain"


# --- pure helpers (unit-tested) ----------------------------------------------


def shannon_entropy(counts: list[int]) -> float:
    """Shannon entropy (in bits) of a distribution given its bucket counts."""
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _quartile_bucket_labels(numbers: list[float]) -> list[str]:
    """Assign each number to a quartile bucket ``Q1..Q4`` using the 3 quartile
    cut points of the distribution."""
    q1, q2, q3 = statistics.quantiles(numbers, n=4)
    labels: list[str] = []
    for value in numbers:
        if value <= q1:
            labels.append("Q1")
        elif value <= q2:
            labels.append("Q2")
        elif value <= q3:
            labels.append("Q3")
        else:
            labels.append("Q4")
    return labels


def bucket_field_values(values: list[Any]) -> Counter[str]:
    """Bucket a field's raw values into labelled buckets and count them.

    Continuous numeric fields (typed number, not bool, > 4 distinct values) are
    quartile-bucketed; everything else is categorical. Missing/null values form
    their own :data:`MISSING_BUCKET`.
    """
    counts: Counter[str] = Counter()
    present = [v for v in values if v is not None]
    missing = len(values) - len(present)

    numeric = [float(v) for v in present if _is_number(v)]
    is_numeric_field = bool(present) and len(numeric) == len(present)

    if is_numeric_field and len(set(numeric)) >= _MIN_DISTINCT_FOR_QUARTILES:
        for label in _quartile_bucket_labels(numeric):
            counts[label] += 1
    else:
        for value in present:
            counts[str(value)] += 1

    if missing:
        counts[MISSING_BUCKET] = missing
    return counts


def get_dotted(record: dict[str, Any], path: str) -> Any:
    """Return ``record[a][b][...]`` for a dotted ``path`` (``"a.b.c"``), or
    ``None`` if any segment is missing or a non-dict is encountered."""
    current: Any = record
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def resolve_slot_fields(slot: SlotDef, catalog_field_map: dict[str, str]) -> list[str]:
    """Resolve a slot's ``catalog_field`` (``None`` | str | list) to dotted
    catalog paths.

    Each entry is either a key of ``catalog_field_map`` (resolved to its mapped
    path) or an already-dotted path (used as-is) — the real YAMLs use the latter
    form directly, so both are supported.
    """
    raw = slot.catalog_field
    if raw is None:
        return []
    entries = [raw] if isinstance(raw, str) else list(raw)
    return [catalog_field_map.get(entry, entry) for entry in entries]


# --- category computation -----------------------------------------------------


def _field_entropy(records: list[dict[str, Any]], path: str) -> dict[str, Any]:
    values = [get_dotted(rec, path) for rec in records]
    counts = bucket_field_values(values)
    return {
        "path": path,
        "entropy": round(shannon_entropy(list(counts.values())), 4),
        "n_buckets": len(counts),
        "n_missing": counts.get(MISSING_BUCKET, 0),
    }


def _slot_information_gain(
    records: list[dict[str, Any]], slot: SlotDef, catalog_field_map: dict[str, str]
) -> dict[str, Any] | None:
    """Compute the information-gain entry for one optional slot, or ``None`` if
    the slot has no backing catalog field to score."""
    paths = resolve_slot_fields(slot, catalog_field_map)
    if not paths:
        return None

    fields = {path: _field_entropy(records, path) for path in paths}
    mean_entropy = statistics.fmean(f["entropy"] for f in fields.values())
    return {
        "entropy": round(mean_entropy, 4),
        "n_samples": len(records),
        "priority_rank": slot.priority_rank,
        "fields": fields,
    }


def load_catalog(category_key: str) -> list[dict[str, Any]]:
    """Load the processed catalog records for a category."""
    path = _CATALOG_DIR / f"{category_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"No catalog file at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of records in {path}")
    return data


def compute_category(category_key: str) -> dict[str, Any]:
    """Compute the information-gain artifact for one category."""
    profile: SlotProfile = load_slot_profile(category_key)
    records = load_catalog(category_key)

    result: dict[str, Any] = {}
    unscored: list[str] = []
    for slot in profile.optional_slots:
        entry = _slot_information_gain(records, slot, profile.catalog_field_map)
        if entry is None:
            unscored.append(slot.name)
        else:
            result[slot.name] = entry

    ranked = sorted(result, key=lambda name: result[name]["entropy"], reverse=True)
    result["ranked_slots"] = ranked
    result["_meta"] = {
        "category_key": category_key,
        "category_label": profile.category_label,
        "n_records": len(records),
        "unscored_slots": unscored,
        "generated_by": "scripts/compute_information_gain.py",
    }
    return result


def _print_table(category_key: str, result: dict[str, Any]) -> None:
    meta = result["_meta"]
    print(f"\n=== {category_key} ({meta['category_label']}) — n={meta['n_records']} ===")
    print(f"{'rank':>4}  {'slot':<20} {'entropy':>8}  {'buckets':>7}  fields")
    for position, name in enumerate(result["ranked_slots"], start=1):
        entry = result[name]
        buckets = sum(f["n_buckets"] for f in entry["fields"].values())
        paths = ", ".join(entry["fields"])
        print(f"{position:>4}  {name:<20} {entry['entropy']:>8.4f}  {buckets:>7}  {paths}")
    if meta["unscored_slots"]:
        print(f"      unscored (no catalog_field): {', '.join(meta['unscored_slots'])}")


def _write_output(category_key: str, result: dict[str, Any]) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{category_key}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    categories = args or available_categories()

    written: list[Path] = []
    for category_key in categories:
        try:
            result = compute_category(category_key)
        except FileNotFoundError as exc:
            print(f"[skip] {category_key}: {exc}", file=sys.stderr)
            continue
        _print_table(category_key, result)
        written.append(_write_output(category_key, result))

    print(f"\nWrote {len(written)} file(s) to {_OUTPUT_DIR}")
    for path in written:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
