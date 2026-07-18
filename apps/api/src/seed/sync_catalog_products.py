"""Synchronize the real air-conditioner catalog into the API read model.

The raw ``air_conditioners`` table is created by ``scripts/import_catalog.py``.
This module maps it to the normalized tables consumed by the existing API and
web application. It intentionally uses neutral values for fields absent from
the source (for example price 0 means "contact us", not a free product).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, joinedload

from src.core.database import SessionLocal
from src.models import Category, Inventory, Price, Product, ProductSpec, Promotion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    source_rows: int
    created: int
    updated: int
    deleted: int


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_value = ascii_value.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def _price(value: Any) -> Decimal:
    if value is None or _text(value) == "":
        return Decimal("0")
    return Decimal(str(value))


def _first_number(value: Any) -> float | None:
    numbers = re.findall(r"\d+(?:[.,]\d+)?", _text(value))
    if not numbers:
        return None
    return min(float(number.replace(",", ".")) for number in numbers)


def _capacity_btu(value: Any) -> int:
    match = re.search(r"(\d[\d.,]*)\s*BTU", _text(value), re.IGNORECASE)
    if not match:
        return 0
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else 0


def _area_range(value: Any) -> tuple[int, int]:
    source = _text(value).lower()
    area_part = source.split("m²", 1)[0]
    numbers = [int(number) for number in re.findall(r"\d+", area_part)]
    if not numbers:
        return 0, 0
    if "dưới" in source:
        return 0, numbers[0]
    if "trên" in source:
        return numbers[0], numbers[0] + 20
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    return 0, numbers[0]


def _warranty_months(value: Any) -> int:
    source = _text(value).lower()
    match = re.search(r"(\d+)\s*(năm|tháng)", source)
    if not match:
        return 0
    amount = int(match.group(1))
    return amount * 12 if match.group(2) == "năm" else amount


def _description(row: Mapping[str, Any]) -> str:
    parts = [
        _text(row.get("loai_may")),
        _text(row.get("pham_vi_su_dung")),
        _text(row.get("cong_nghe_lam_lanh")),
        _text(row.get("cong_nghe_tiet_kiem_dien")),
    ]
    available = [part for part in parts if part]
    return " · ".join(available) or "Thông tin kỹ thuật từ catalog sản phẩm thực tế."


def _mapped_values(row: Mapping[str, Any]) -> dict[str, Any]:
    sku = _text(row.get("sku")) or f"catalog-{row['id']}"
    brand = _text(row.get("brand")) or "Chưa xác định"
    model_code = _text(row.get("model_code")) or sku
    original_price = _price(row.get("gia_goc"))
    sale_price = _price(row.get("gia_khuyen_mai")) or original_price
    if original_price == 0:
        original_price = sale_price
    if sale_price > original_price:
        original_price = sale_price
    area_min, area_max = _area_range(row.get("pham_vi_su_dung"))
    promotion = _text(row.get("khuyen_mai_qua"))
    capacity_btu = _capacity_btu(row.get("cong_suat_dau_ra"))
    return {
        "sku": sku,
        "slug": f"may-lanh-{_slugify(brand)}-{_slugify(model_code)}-{sku}",
        "name": f"Máy lạnh {brand} {model_code}",
        "brand": brand,
        "short_description": _description(row),
        "image_url": "",
        "featured": sale_price > 0 and bool(promotion),
        "rating": 0.0,
        "review_count": 0,
        "original_price": original_price,
        "sale_price": sale_price,
        "capacity_btu": capacity_btu,
        "horsepower": round(capacity_btu / 9000, 1) if capacity_btu else 0.0,
        "recommended_area_min": area_min,
        "recommended_area_max": area_max,
        "inverter": "không inverter" not in _text(row.get("loai_inverter")).lower()
        and "inverter" in _text(row.get("loai_inverter")).lower(),
        "noise_db": _first_number(row.get("do_on")),
        "energy_rating": _text(row.get("nhan_nang_luong")) or "Chưa có dữ liệu",
        "warranty_months": _warranty_months(row.get("bao_hanh_bo_phan")),
        "promotion": promotion,
    }


def _apply_values(product: Product, values: Mapping[str, Any], category: Category) -> None:
    product.sku = values["sku"]
    product.slug = values["slug"]
    product.name = values["name"]
    product.brand = values["brand"]
    product.category = category
    product.short_description = values["short_description"]
    product.image_url = values["image_url"]
    product.featured = values["featured"]
    product.rating = values["rating"]
    product.review_count = values["review_count"]

    if product.specs is None:
        product.specs = ProductSpec()
    product.specs.capacity_btu = values["capacity_btu"]
    product.specs.horsepower = values["horsepower"]
    product.specs.recommended_area_min = values["recommended_area_min"]
    product.specs.recommended_area_max = values["recommended_area_max"]
    product.specs.inverter = values["inverter"]
    product.specs.noise_db = values["noise_db"]
    product.specs.energy_rating = values["energy_rating"]
    product.specs.warranty_months = values["warranty_months"]

    if product.price is None:
        product.price = Price(currency="VND")
    product.price.original_price = values["original_price"]
    product.price.sale_price = values["sale_price"]
    product.price.currency = "VND"

    if product.inventory is None:
        product.inventory = Inventory()
    product.inventory.stock_status = "unknown"
    product.inventory.stock_quantity = 0

    promotion = values["promotion"]
    if promotion:
        if product.promotion is None:
            product.promotion = Promotion()
        product.promotion.title = "Ưu đãi kèm sản phẩm"
        product.promotion.description = promotion
    elif product.promotion is not None:
        product.promotion = None


def sync_real_air_conditioners(db: Session) -> SyncResult:
    """Upsert real rows and remove stale/demo air-conditioner products atomically."""

    if not inspect(db.get_bind()).has_table("air_conditioners"):
        raise RuntimeError(
            "Bảng air_conditioners chưa tồn tại. Hãy chạy scripts/import_catalog.py trước."
        )

    category = db.scalar(select(Category).where(Category.slug == "may-lanh"))
    if category is None:
        category = Category(name="Máy lạnh", slug="may-lanh")
        db.add(category)
        db.flush()
    else:
        category.name = "Máy lạnh"

    source_rows = list(db.execute(text("SELECT * FROM air_conditioners ORDER BY id")).mappings())
    existing = list(
        db.scalars(
            select(Product)
            .where(Product.category_id == category.id)
            .options(
                joinedload(Product.specs),
                joinedload(Product.price),
                joinedload(Product.inventory),
                joinedload(Product.promotion),
            )
        ).unique()
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # The legacy demo seed assigned product IDs explicitly, so PostgreSQL's
        # sequence can still point at 1 even when rows 1..20 already exist.
        db.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('products', 'id'), "
                "COALESCE((SELECT MAX(id) FROM products), 0) + 1, false)"
            )
        )
    by_sku = {product.sku: product for product in existing}
    source_skus: set[str] = set()
    created = 0
    updated = 0

    for row in source_rows:
        values = _mapped_values(dict(row))
        sku = values["sku"]
        source_skus.add(sku)
        product = by_sku.get(sku)
        if product is None:
            product = Product()
            db.add(product)
            created += 1
        else:
            updated += 1
        _apply_values(product, values, category)

    stale = [product for product in existing if product.sku not in source_skus]
    for product in stale:
        db.delete(product)
    db.commit()
    return SyncResult(len(source_rows), created, updated, len(stale))


def main() -> None:
    with SessionLocal() as db:
        try:
            result = sync_real_air_conditioners(db)
        except Exception:
            db.rollback()
            logger.exception("Không thể đồng bộ catalog thật")
            raise
    print(
        "Real catalog sync complete: "
        f"source={result.source_rows} created={result.created} "
        f"updated={result.updated} deleted={result.deleted}"
    )


if __name__ == "__main__":
    main()
