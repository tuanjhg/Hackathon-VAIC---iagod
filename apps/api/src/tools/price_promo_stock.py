"""Tool: price_promo_stock (ADR A5, `docs/pipelines.md` §6.5).

Adapter reading price/promotion/stock facts for candidate SKUs directly from
`data/realdata/processed/*.json` (the ETL'd Điện Máy Xanh export — see
`data/realdata/NOTES.md`), not from Postgres: per S4's design
(`docs/pipelines.md` §6.4 point 4), price/promo/stock are fetched fresh per
request ("facts JSON... nguồn sự thật duy nhất cho S5–S8"), while Postgres
only holds the catalog snapshot used for SQL filtering.

Every field is wrapped with provenance ``{value, source, fetched_at}`` per
`docs/research/dmx-guardrail-design.md` §2 (Tầng 0 — Data): "fact nào cũng
mang provenance; null là null". Two honesty consequences of the real data
(see NOTES.md):

- ``stock``: this dataset has **no inventory/stock field at all** in any of
  the 14 categories. Returning a fabricated status would violate the
  honesty guardrail (Tầng 3) — ``stock`` is therefore always ``null`` with
  ``source.dataset = "unavailable"`` rather than invented.
- ``original_price``/``sale_price``: ``null`` whenever the source record's
  own ``has_price_data`` is ``False`` (price coverage is sparse by design —
  13–73% depending on category), never backfilled with a guess.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.config import Settings, get_settings

PRICE_PROMO_STOCK_SCHEMA: dict[str, Any] = {
    "name": "price_promo_stock",
    "description": (
        "Trả giá, khuyến mãi và tồn kho cho một hoặc nhiều SKU sản phẩm, mỗi "
        "field kèm provenance (nguồn dữ liệu + thời điểm lấy). Field không có "
        "dữ liệu trả về null, không suy diễn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skus": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sách SKU sản phẩm cần tra cứu.",
            }
        },
        "required": ["skus"],
    },
}


@dataclass(frozen=True)
class Fact:
    """A single provenance-wrapped value, per the guardrail-doc shape."""

    value: Any
    source: dict[str, str]
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source, "fetched_at": self.fetched_at}


@dataclass(frozen=True)
class ProductFacts:
    sku: str
    original_price: Fact
    sale_price: Fact
    promotions: Fact
    stock: Fact

    def to_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "original_price": self.original_price.to_dict(),
            "sale_price": self.sale_price.to_dict(),
            "promotions": self.promotions.to_dict(),
            "stock": self.stock.to_dict(),
        }


class PricePromoStockTool:
    """In-memory adapter over ``data/realdata/processed/*.json``, indexed by
    SKU (the true unique key — ``model_code`` is not unique, per NOTES.md).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._index: dict[str, dict[str, Any]] | None = None

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if self._index is not None:
            return self._index
        base = Path(self._settings.realdata_processed_path)
        index: dict[str, dict[str, Any]] = {}
        for path in sorted(base.glob("*.json")):
            if path.stem.startswith("_"):
                continue  # _summary.json / _demo_ready_priority.json aren't category files
            records = json.loads(path.read_text(encoding="utf-8"))
            for record in records:
                index[record["sku"]] = {**record, "_dataset": path.stem}
        self._index = index
        return index

    def get_facts(self, sku: str) -> ProductFacts | None:
        """Return provenance-wrapped facts for one SKU, or ``None`` if the
        SKU doesn't exist in the catalog at all (distinct from a known SKU
        with missing price data, which returns ``null`` fields instead).
        """
        record = self._load_index().get(sku)
        if record is None:
            return None

        fetched_at = self._clock().isoformat()
        dataset = record["_dataset"]

        def fact(field: str, value: Any) -> Fact:
            return Fact(
                value=value,
                source={"dataset": dataset, "row": sku, "field": field},
                fetched_at=fetched_at,
            )

        has_price = bool(record.get("has_price_data"))
        return ProductFacts(
            sku=sku,
            original_price=fact("original_price", record.get("original_price") if has_price else None),
            sale_price=fact("sale_price", record.get("sale_price") if has_price else None),
            promotions=fact("promotions", record.get("promotions") or []),
            stock=Fact(
                value=None,
                source={"dataset": "unavailable", "row": sku, "field": "stock"},
                fetched_at=fetched_at,
            ),
        )

    async def get_facts_many(self, skus: list[str]) -> dict[str, ProductFacts | None]:
        """Fan-out entry point matching S4's per-candidate ``asyncio.gather``
        usage (`docs/pipelines.md` §6.4 point 4). Reading is in-memory (no
        network I/O), so this is synchronous underneath — the async
        signature exists so callers can ``asyncio.gather`` this alongside
        the other (genuinely async) S4 tools without a special case.
        """
        return {sku: self.get_facts(sku) for sku in skus}
