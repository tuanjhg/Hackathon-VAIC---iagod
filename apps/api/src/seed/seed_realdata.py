"""Seed data/realdata/processed/*.json (14 real Điện Máy Xanh categories, see
data/realdata/NOTES.md) into Postgres — task 14.

Populates ``products`` (``category_key`` + ``specs``/``specs_raw`` JSONB, from
migration 20260718_0002) and, only for records with ``has_price_data``, a
matching ``prices`` row — price coverage is sparse by design (13–73%
depending on category; see data/realdata/raw/profile_report.md), so most
products legitimately have no price row rather than a fabricated one.

Deliberately does **not** create ``inventory`` rows (this dataset has no
stock field at all in any category, confirmed in NOTES.md) or ``promotions``
rows (the source ``promotions`` field is a list of free-text strings, not the
single title/description shape the ``promotions`` table expects — price/promo
freshness is instead served live by the ``price_promo_stock`` tool, which
reads these same JSON files directly; see docs/pipelines.md §6.4 point 4 and
src/tools/price_promo_stock.py). ``ProductRepository.list_products()``
inner-joins on price/specs/inventory (src/repositories/product_repository.py),
so these multi-category products are naturally excluded from the existing
`/api/v1/products` listing until the catalog_search tool (task 10, separate
work) is wired up — this seed is additive and never affects the aircon demo
flow that `seed_products.py` populates.

Note: for category_key "may_lanh" this seed reuses the *same* Category row
`seed_products.py` creates (slug "may-lanh") rather than creating a second
"Máy lạnh" category — one real-world category should map to one row
regardless of which seed populated it. The 20 demo products (with
ProductSpec+Price+Inventory) and the ~1000 realdata-only products (specs
JSONB only) coexist under it; the inner-join above is what keeps them from
mixing in existing read paths.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import SessionLocal
from src.models import Category, Price, Product

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def _resync_postgres_id_sequence(db: Session) -> None:
    """`seed_products.py` inserts `products.id` explicitly (from
    data/demo/products.json's own ids), which never advances the
    `products_id_seq` sequence backing the autoincrement default. Without
    this, this seed's autoincrement inserts collide with those explicit ids
    (e.g. a fresh DB's sequence is still at 1, but id=1 already exists).
    No-op on SQLite, which has no separate sequence object to desync.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text(
            "SELECT setval('products_id_seq', "
            "COALESCE((SELECT MAX(id) FROM products), 0) + 1, false)"
        )
    )


def _short_description(record: dict[str, Any]) -> str:
    brand = record.get("brand") or ""
    label = record.get("category_label") or ""
    model_code = record.get("model_code") or ""
    return f"{label} {brand}, mã {model_code}".strip()


def seed_realdata(db: Session, categories_dir: Path) -> int:
    _resync_postgres_id_sequence(db)
    created = 0
    for path in sorted(categories_dir.glob("*.json")):
        if path.stem.startswith("_"):
            continue  # _summary.json / _demo_ready_priority.json aren't category files
        records = json.loads(path.read_text(encoding="utf-8"))
        if not records:
            continue

        category_key = records[0]["category_key"]
        category_label = records[0]["category_label"]
        category_slug = _slugify(category_key)
        category = db.scalar(select(Category).where(Category.slug == category_slug))
        if category is None:
            category = Category(name=category_label, slug=category_slug)
            db.add(category)
            db.flush()

        for record in records:
            sku = record["sku"]
            if db.scalar(select(Product).where(Product.sku == sku)):
                continue
            specs = record.get("specs") or {}
            product = Product(
                sku=sku,
                slug=_slugify(sku),
                name=specs.get("display_name")
                or f"{record.get('brand', '')} {category_label}".strip(),
                brand=record.get("brand") or "",
                category=category,
                short_description=_short_description(record),
                image_url="",
                category_key=category_key,
                specs_json=specs,
                specs_raw=record.get("specs_raw") or {},
            )
            if record.get("has_price_data"):
                product.price = Price(
                    original_price=record["original_price"],
                    sale_price=record["sale_price"],
                    currency="VND",
                )
            db.add(product)
            created += 1

    db.commit()
    return created


def main() -> None:
    categories_dir = Path(settings.realdata_processed_path)
    with SessionLocal() as db:
        created = seed_realdata(db, categories_dir)
    logger.info("Seeded %s realdata products", created)
    print(f"Realdata seed complete: {created} new products")


if __name__ == "__main__":
    main()
