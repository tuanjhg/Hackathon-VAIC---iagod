"""Tool: catalog_search (ADR A5, STT10).

Structured-first **hard-filter** half of stage S4 (``docs/pipelines.md`` §6.4
point 1): a SQL filter over the catalog snapshot in Postgres that narrows the
14-category product table down to candidates matching the caller's category,
budget and derived capacity needs, plus a fuzzy name/model lookup.

Scope boundary — the hybrid **vector-rerank** half (§6.4 point 2) is explicitly
OUT of scope (gated behind an ablation study that does not exist yet), so the
``embedding`` / ``search_tsv`` columns that already exist on the table are left
untouched here.

Design notes:

- **Filter derivation is map-driven.** Per-category slot→spec mappings come from
  ``src/pipeline/slots/<category_key>.yaml`` (``catalog_field_map``), so the JSON
  paths this tool reads are not hardcoded. The category-specific *formulas*
  (BTU / litre sizing) genuinely need Python and are hardcoded below — the YAML
  ``derivation_rules`` are human-readable prose, not machine-executable.
- **JSON comparators.** ``specs`` is ``JSON().with_variant(JSONB(), "postgresql")``.
  The SQLAlchemy JSON element comparators ``.as_integer()`` / ``.as_float()`` /
  ``.as_boolean()`` were verified to work against the SQLite test engine
  (SQLAlchemy 2.0.51), so they are used directly — no ``cast()`` fallback needed.
  A missing JSON key yields SQL ``NULL`` and simply fails the comparison (the row
  is excluded) rather than raising, which is the behaviour we want.
- **Budget honesty guardrail.** The budget ceiling (``budget_max`` × 1.05
  headroom, ADR) is applied only to products that HAVE a price row. Products with
  no price data are never excluded by a budget filter — absence of price data is
  not the same as "over budget".
- **Fuzzy name match.** Production uses Postgres ``pg_trgm`` (ADR B4) — not wired
  here (no new dependency, no migration). The portable dev/test fallback is a
  case-insensitive substring match on ``name`` / ``sku`` plus stdlib
  ``difflib.SequenceMatcher`` closeness scoring for typo tolerance.
"""

from __future__ import annotations

import difflib
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from src.models import Price, Product

_SLOTS_DIR = Path(__file__).resolve().parents[1] / "pipeline" / "slots"

# ADR budget headroom: accept priced products up to 5% over the stated budget.
_BUDGET_HEADROOM = 1.05

# Slot keys consumed by category derivation formulas (not direct spec filters).
_DERIVATION_SLOT_KEYS = frozenset({"dien_tich_m2", "nang_truc_tiep", "so_nguoi_dung"})

# difflib fuzzy-match tuning for the name_query fallback.
_NAME_MATCH_THRESHOLD = 0.6
_NAME_CANDIDATE_CAP = 500

TOOL_SCHEMA: dict[str, Any] = {
    "name": "catalog_search",
    "description": (
        "Lọc danh mục sản phẩm theo ngành hàng, ngân sách và nhu cầu suy diễn "
        "(diện tích phòng → công suất BTU cho máy lạnh, số người → dung tích lít "
        "cho tủ lạnh), kèm tra cứu tên/model gần đúng. Sản phẩm không có dữ liệu "
        "giá KHÔNG bị loại bởi bộ lọc ngân sách."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category_key": {
                "type": "string",
                "description": "Khóa ngành hàng ETL, ví dụ 'may_lanh', 'tu_lanh'.",
            },
            "budget_max": {
                "type": ["integer", "null"],
                "description": "Ngân sách tối đa (VND). Áp dụng với headroom 5%.",
            },
            "slots": {
                "type": "object",
                "description": (
                    "Giá trị slot bổ sung (dien_tich_m2, nang_truc_tiep, "
                    "so_nguoi_dung, inverter, ...). Khóa không ánh xạ được bỏ qua."
                ),
            },
            "name_query": {
                "type": ["string", "null"],
                "description": "Chuỗi tên/model tìm gần đúng.",
            },
            "limit": {"type": "integer", "description": "Số kết quả tối đa.", "default": 20},
            "offset": {"type": "integer", "description": "Bỏ qua n kết quả đầu.", "default": 0},
        },
        "required": ["category_key"],
    },
}


@dataclass(frozen=True)
class CatalogSearchResult:
    """Result of a catalog search.

    ``products`` are ORM ``Product`` rows with ``price`` and ``category`` eagerly
    loaded (so consumers can read them after the session closes). ``total_count``
    is the pre-limit match count, consumed by S3's ``candidate_count`` dialogue
    input.
    """

    products: list[Product]
    total_count: int


# --------------------------------------------------------------------------- #
# YAML catalog_field_map loading
# --------------------------------------------------------------------------- #
@functools.cache
def _catalog_field_map(category_key: str) -> dict[str, str]:
    """Return ``catalog_field_map`` (spec concept → ``specs.<field>`` dotted path)
    for a category, or ``{}`` if no slot file exists for it.
    """
    path = _SLOTS_DIR / f"{category_key}.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    field_map = data.get("catalog_field_map") or {}
    return {str(k): str(v) for k, v in field_map.items()}


def _json_key(field_map: dict[str, str], concept: str) -> str | None:
    """Resolve a spec concept to its JSON key via the field map, stripping the
    ``specs.`` prefix. Returns ``None`` when the concept isn't a ``specs.*`` path.
    """
    dotted = field_map.get(concept)
    if dotted is None or not dotted.startswith("specs."):
        return None
    return dotted.split(".", 1)[1]


def _as_number(value: Any) -> float | None:
    """Coerce a slot value (int/float/numeric-string) to float; ``None`` on
    failure. ``bool`` is rejected so an ``inverter`` flag never reads as area.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Filter (WHERE-clause) construction — shared by catalog_search & catalog_count
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Filters:
    conditions: list[ColumnElement[bool]]
    needs_price_join: bool


def _capacity_conditions(
    category_key: str, field_map: dict[str, str], slots: dict[str, Any]
) -> list[ColumnElement[bool]]:
    """Category-specific derived-capacity filters.

    Formulas are hardcoded (docs/pipelines.md §6.4); the JSON paths they read are
    resolved from ``field_map``. Categories with no rule yield no condition.
    """
    if category_key == "may_lanh":
        return _may_lanh_capacity(field_map, slots)
    if category_key == "tu_lanh":
        return _tu_lanh_capacity(field_map, slots)
    return []


def _may_lanh_capacity(
    field_map: dict[str, str], slots: dict[str, Any]
) -> list[ColumnElement[bool]]:
    """máy lạnh sizing.

    Prefer the direct area-range check ``area_min <= dien_tich <= area_max`` when
    both spec fields exist on a record; otherwise fall back per-record to the BTU
    proxy ``capacity_btu >= dien_tich * 600 * (1.3 if nang_truc_tiep else 1.0)``.
    """
    dien_tich = _as_number(slots.get("dien_tich_m2"))
    if dien_tich is None:
        return []

    nang_truc_tiep = bool(slots.get("nang_truc_tiep"))
    btu_can = dien_tich * 600 * (1.3 if nang_truc_tiep else 1.0)

    area_min_key = _json_key(field_map, "recommended_area_min")
    area_max_key = _json_key(field_map, "recommended_area_max")
    btu_key = _json_key(field_map, "capacity_btu")

    if area_min_key and area_max_key and btu_key:
        area_min = Product.specs_json[area_min_key].as_float()
        area_max = Product.specs_json[area_max_key].as_float()
        capacity_btu = Product.specs_json[btu_key].as_integer()
        area_present = and_(area_min.isnot(None), area_max.isnot(None))
        area_check = and_(area_present, area_min <= dien_tich, area_max >= dien_tich)
        # BTU fallback applies only when the area range is absent for the record.
        btu_check = and_(
            or_(area_min.is_(None), area_max.is_(None)), capacity_btu >= btu_can
        )
        return [or_(area_check, btu_check)]

    if btu_key:
        return [Product.specs_json[btu_key].as_integer() >= btu_can]

    return []


def _tu_lanh_capacity(
    field_map: dict[str, str], slots: dict[str, Any]
) -> list[ColumnElement[bool]]:
    """tủ lạnh sizing: ``lit_can = 45 * so_nguoi_dung + 100`` (docs §6.4 midpoint),
    filter ``capacity_total_l >= lit_can``.
    """
    so_nguoi = _as_number(slots.get("so_nguoi_dung"))
    if so_nguoi is None:
        return []
    lit_can = 45 * so_nguoi + 100
    total_key = _json_key(field_map, "capacity_total_l")
    if total_key is None:
        return []
    return [Product.specs_json[total_key].as_float() >= lit_can]


def _direct_conditions(
    field_map: dict[str, str], slots: dict[str, Any]
) -> list[ColumnElement[bool]]:
    """Direct equality filters for scalar slots that map (via ``field_map``) to a
    ``specs.*`` field. Currently boolean flags (e.g. ``inverter``); slots that
    don't map to anything are ignored. Derivation slots are handled elsewhere.
    """
    conditions: list[ColumnElement[bool]] = []
    for key, value in slots.items():
        if key in _DERIVATION_SLOT_KEYS:
            continue
        json_key = _json_key(field_map, key)
        if json_key is None:
            continue
        if isinstance(value, bool):
            conditions.append(Product.specs_json[json_key].as_boolean() == value)
        # Numeric / string direct filters are not required by S4 yet; skipping
        # them keeps unmapped or unsupported slot values a safe no-op.
    return conditions


def _build_filters(
    category_key: str, budget_max: int | None, slots: dict[str, Any] | None
) -> _Filters:
    field_map = _catalog_field_map(category_key)
    slot_values = slots or {}

    conditions: list[ColumnElement[bool]] = [Product.category_key == category_key]
    needs_price_join = False

    if budget_max is not None:
        threshold = int(round(budget_max * _BUDGET_HEADROOM))
        # Honesty guardrail: keep unpriced products (no Price row) unconditionally.
        conditions.append(or_(Price.id.is_(None), Price.sale_price <= threshold))
        needs_price_join = True

    conditions.extend(_capacity_conditions(category_key, field_map, slot_values))
    conditions.extend(_direct_conditions(field_map, slot_values))

    return _Filters(conditions=conditions, needs_price_join=needs_price_join)


def _count(db: Session, filters: _Filters) -> int:
    stmt = select(func.count(Product.id)).select_from(Product)
    if filters.needs_price_join:
        # Explicit ON clause (not the relationship) so it doesn't collide with any
        # eager-load join on the same table.
        stmt = stmt.outerjoin(Price, Price.product_id == Product.id)
    stmt = stmt.where(*filters.conditions)
    return int(db.scalar(stmt) or 0)


# --------------------------------------------------------------------------- #
# Fuzzy name matching (pg_trgm production path; difflib dev/test fallback)
# --------------------------------------------------------------------------- #
def _name_matches(product: Product, query: str) -> bool:
    name = (product.name or "").lower()
    sku = (product.sku or "").lower()
    if query in name or query in sku or (name and name in query):
        return True
    whole = difflib.SequenceMatcher(None, query, name).ratio()
    best_token = max(
        (difflib.SequenceMatcher(None, query, token).ratio() for token in name.split()),
        default=0.0,
    )
    return max(whole, best_token) >= _NAME_MATCH_THRESHOLD


def _fuzzy_filter(products: list[Product], name_query: str) -> list[Product]:
    query = name_query.strip().lower()
    if not query:
        return products
    return [p for p in products if _name_matches(p, query)]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def catalog_search(
    db: Session,
    *,
    category_key: str,
    budget_max: int | None = None,
    slots: dict[str, Any] | None = None,
    name_query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> CatalogSearchResult:
    """Structured hard-filter search over the catalog snapshot.

    See module docstring for the budget honesty guardrail and fuzzy-match notes.
    """
    filters = _build_filters(category_key, budget_max, slots)

    stmt = (
        select(Product)
        .options(joinedload(Product.price), joinedload(Product.category))
        .order_by(Product.id)
    )
    if filters.needs_price_join:
        stmt = stmt.outerjoin(Price, Price.product_id == Product.id)
    stmt = stmt.where(*filters.conditions)

    if name_query and name_query.strip():
        # Fetch a bounded candidate set, then apply the portable fuzzy filter in
        # Python (substring + difflib). Count/pagination happen post-filter here
        # since typo tolerance can't be expressed in portable SQL without pg_trgm.
        candidates = list(db.scalars(stmt.limit(_NAME_CANDIDATE_CAP)).unique().all())
        matched = _fuzzy_filter(candidates, name_query)
        page = matched[offset : offset + limit]
        return CatalogSearchResult(products=page, total_count=len(matched))

    total = _count(db, filters)
    rows = db.scalars(stmt.limit(limit).offset(offset)).unique().all()
    return CatalogSearchResult(products=list(rows), total_count=total)


def catalog_count(
    db: Session,
    *,
    category_key: str,
    budget_max: int | None = None,
    slots: dict[str, Any] | None = None,
) -> int:
    """Pre-limit match count for the same structured filters, without fetching
    rows. Used by S3's dialogue policy (``candidate_count``) where only the count
    is needed. ``name_query`` is intentionally not a parameter — the fuzzy count
    would require fetching rows anyway, defeating the purpose.
    """
    return _count(db, _build_filters(category_key, budget_max, slots))
