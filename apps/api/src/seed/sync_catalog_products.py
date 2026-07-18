"""Synchronize all 14 raw catalog tables into the API read model.

The raw tables are created by ``scripts/import_catalog.py``. Shared product
fields are mapped to relational columns, while category-specific attributes
are preserved in ``products.specifications``. Legacy air-conditioner fields
remain populated so existing API clients continue to work.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, joinedload

from src.core.database import SessionLocal
from src.models import Category, Inventory, Price, Product, ProductSpec, Promotion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogCategory:
    """Mapping between one raw source table and its public API category."""

    table_name: str
    name: str
    slug: str


CATALOG_CATEGORIES: tuple[CatalogCategory, ...] = (
    CatalogCategory("refrigerators", "Tủ lạnh", "tu-lanh"),
    CatalogCategory("air_conditioners", "Máy lạnh", "may-lanh"),
    CatalogCategory("washing_machines", "Máy giặt", "may-giat"),
    CatalogCategory("clothes_dryers", "Máy sấy quần áo", "may-say-quan-ao"),
    CatalogCategory("dishwashers", "Máy rửa chén", "may-rua-chen"),
    CatalogCategory("coolers_freezers", "Tủ mát, tủ đông", "tu-mat-tu-dong"),
    CatalogCategory("water_heaters", "Máy nước nóng", "may-nuoc-nong"),
    CatalogCategory("karaoke_microphones", "Micro karaoke", "micro-karaoke"),
    CatalogCategory(
        "phone_recording_microphones",
        "Micro thu âm điện thoại",
        "micro-thu-am-dien-thoai",
    ),
    CatalogCategory("smartwatches", "Đồng hồ thông minh", "dong-ho-thong-minh"),
    CatalogCategory("desktop_computers", "Máy tính để bàn", "may-tinh-de-ban"),
    CatalogCategory("computer_monitors", "Màn hình máy tính", "man-hinh-may-tinh"),
    CatalogCategory("printers", "Máy in", "may-in"),
    CatalogCategory("tablets", "Máy tính bảng", "may-tinh-bang"),
)

SYSTEM_COLUMNS = {
    "id",
    "source_row_id",
    "category_name",
    "source_file",
    "data_hash",
    "created_at",
    "updated_at",
}
SHARED_COLUMNS = {
    "model_code",
    "sku",
    "productidweb",
    "category_code",
    "brand_id",
    "brand",
    "gia_goc",
    "gia_khuyen_mai",
    "khuyen_mai_qua",
}


@dataclass(frozen=True)
class SyncResult:
    source_rows: int
    created: int
    updated: int
    deleted: int
    categories: int = 0


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


def _json_value(value: Any) -> Any:
    """Convert database-native values to lossless JSON-compatible values."""

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return value


def _specifications(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _json_value(value)
        for key, value in row.items()
        if key not in SYSTEM_COLUMNS | SHARED_COLUMNS and value is not None and _text(value) != ""
    }


def _description(
    row: Mapping[str, Any], category: CatalogCategory, brand: str, model_code: str
) -> str:
    preferred_keys = (
        "loai_san_pham",
        "loai_may",
        "pham_vi_su_dung",
        "cong_nghe",
        "cong_nghe_lam_lanh",
        "cong_nghe_tiet_kiem_dien",
        "kich_thuoc_man_hinh",
        "dung_tich_tong",
        "khoi_luong_tai_chinh",
    )
    details = [_text(row.get(key)) for key in preferred_keys if _text(row.get(key))]
    if details:
        return " · ".join(dict.fromkeys(details))
    return f"{category.name} {brand} {model_code} từ catalog sản phẩm thực tế."


def _map_row(row: Mapping[str, Any], category: CatalogCategory) -> dict[str, Any]:
    fallback_sku = f"{category.slug}-{row['id']}"
    sku = _text(row.get("sku")) or fallback_sku
    brand = _text(row.get("brand")) or "Chưa xác định"
    model_code = _text(row.get("model_code")) or sku
    original_price = _price(row.get("gia_goc"))
    sale_price = _price(row.get("gia_khuyen_mai")) or original_price
    if original_price == 0:
        original_price = sale_price
    if sale_price > original_price:
        original_price = sale_price

    is_air_conditioner = category.table_name == "air_conditioners"
    area_min, area_max = _area_range(row.get("pham_vi_su_dung")) if is_air_conditioner else (0, 0)
    capacity_btu = _capacity_btu(row.get("cong_suat_dau_ra")) if is_air_conditioner else 0
    inverter_source = _text(row.get("loai_inverter")).lower()
    promotion = _text(row.get("khuyen_mai_qua"))
    warranty_source = row.get("bao_hanh_bo_phan") or row.get("bao_hanh_dong_co")

    return {
        "sku": sku,
        "slug": f"{category.slug}-{_slugify(brand)}-{_slugify(model_code)}-{_slugify(sku)}",
        "name": f"{category.name} {brand} {model_code}",
        "brand": brand,
        "short_description": _description(row, category, brand, model_code),
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
        "inverter": "không inverter" not in inverter_source and "inverter" in inverter_source,
        "noise_db": _first_number(row.get("do_on")) if is_air_conditioner else None,
        "energy_rating": _text(row.get("nhan_nang_luong")) or "Chưa có dữ liệu",
        "warranty_months": _warranty_months(warranty_source),
        "promotion": promotion,
        "specifications": _specifications(row),
    }


def _mapped_values(row: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible air-conditioner mapper used by existing tests/tools."""

    return _map_row(row, CATALOG_CATEGORIES[1])


def _apply_values(product: Product, values: Mapping[str, Any], category: Category) -> None:
    product.sku = values["sku"]
    product.slug = values["slug"]
    product.name = values["name"]
    product.display_name = values["name"]
    product.brand = values["brand"]
    product.category = category
    product.short_description = values["short_description"]
    product.image_url = values["image_url"]
    product.featured = values["featured"]
    product.rating = values["rating"]
    product.review_count = values["review_count"]
    product.specifications = values["specifications"]
    product.source_data = {"source_category": category.code}

    if product.specs is None:
        product.specs = ProductSpec()
    product.specs.raw_specs = values["specifications"]
    product.specs.normalized_specs = {}
    product.specs.search_text = " ".join(
        (values["name"], values["brand"], values["short_description"])
    )
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


def _ensure_categories(
    db: Session, configs: Sequence[CatalogCategory]
) -> dict[str, Category]:
    existing = {
        item.slug: item
        for item in db.scalars(select(Category).where(Category.slug.in_([c.slug for c in configs])))
    }
    for config in configs:
        category = existing.get(config.slug)
        if category is None:
            category = Category(code=config.table_name, name=config.name, slug=config.slug)
            db.add(category)
            existing[config.slug] = category
        else:
            category.code = config.table_name
            category.name = config.name
    db.flush()
    return existing


def sync_catalog_products(
    db: Session, configs: Sequence[CatalogCategory] = CATALOG_CATEGORIES
) -> SyncResult:
    """Atomically upsert all configured raw tables into the API read model."""

    inspector = inspect(db.get_bind())
    missing = [config.table_name for config in configs if not inspector.has_table(config.table_name)]
    if missing:
        raise RuntimeError(
            "Thiếu bảng raw: " + ", ".join(missing) + ". Hãy chạy scripts/import_catalog.py trước."
        )

    categories = _ensure_categories(db, configs)
    category_ids = [categories[config.slug].id for config in configs]
    existing_products = list(
        db.scalars(
            select(Product)
            .where(Product.category_id.in_(category_ids))
            .options(
                joinedload(Product.specs),
                joinedload(Product.price),
                joinedload(Product.inventory),
                joinedload(Product.promotion),
            )
        ).unique()
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('products', 'id'), "
                "COALESCE((SELECT MAX(id) FROM products), 0) + 1, false)"
            )
        )

    by_sku = {product.sku: product for product in existing_products}
    source_skus: set[str] = set()
    source_rows = created = updated = 0

    for config in configs:
        rows = db.execute(text(f'SELECT * FROM "{config.table_name}" ORDER BY id')).mappings()
        category_count = 0
        for row in rows:
            values = _map_row(dict(row), config)
            sku = values["sku"]
            if sku in source_skus:
                raise RuntimeError(f"SKU trùng giữa các bảng raw: {sku}")
            source_skus.add(sku)
            product = by_sku.get(sku)
            if product is None:
                product = Product()
                db.add(product)
                by_sku[sku] = product
                created += 1
            else:
                updated += 1
            _apply_values(product, values, categories[config.slug])
            source_rows += 1
            category_count += 1
        logger.info(
            "Synced source table=%s category=%s rows=%d",
            config.table_name,
            config.slug,
            category_count,
        )

    stale = [product for product in existing_products if product.sku not in source_skus]
    for product in stale:
        db.delete(product)
    db.commit()
    return SyncResult(source_rows, created, updated, len(stale), len(configs))


def sync_real_air_conditioners(db: Session) -> SyncResult:
    """Compatibility entry point for callers that only synchronize air conditioners."""

    return sync_catalog_products(db, (CATALOG_CATEGORIES[1],))


def main() -> None:
    with SessionLocal() as db:
        try:
            result = sync_catalog_products(db)
        except Exception:
            db.rollback()
            logger.exception("Không thể đồng bộ catalog thật")
            raise
    print(
        "Real catalog sync complete: "
        f"categories={result.categories} source={result.source_rows} "
        f"created={result.created} updated={result.updated} deleted={result.deleted}"
    )


if __name__ == "__main__":
    main()
