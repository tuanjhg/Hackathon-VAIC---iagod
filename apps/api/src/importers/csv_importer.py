from __future__ import annotations

import argparse
import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from src.core.database import SessionLocal
from src.db.seed import seed_catalog_metadata
from src.importers.category_registry import (
    CATEGORY_REGISTRY,
    AttributeConfig,
    CategoryConfig,
    category_for_file,
)
from src.importers.normalizers.common import (
    normalize_brand,
    normalize_empty_value,
    normalize_text,
    parse_list,
    parse_price,
)
from src.models import (
    AttributeDefinition,
    Brand,
    Category,
    ImportBatch,
    Inventory,
    Price,
    Product,
    ProductAttributeValue,
    ProductOffer,
    ProductSpec,
    Promotion,
    RawProductRow,
)

logger = logging.getLogger(__name__)

COMMON_COLUMNS = {
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
ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "windows-1252")


@dataclass(slots=True)
class ImportOptions:
    dry_run: bool = False
    limit: int | None = None
    batch_size: int = 300
    update_existing: bool = True
    skip_existing: bool = False
    fail_fast: bool = False


@dataclass(slots=True)
class ImportReport:
    source_file: str
    category_code: str
    total_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0
    warnings: int = 0


@dataclass(slots=True)
class NormalizedRow:
    raw_specs: dict[str, Any]
    normalized_specs: dict[str, Any]
    typed_values: dict[str, tuple[AttributeConfig, Any, str]]
    warnings: list[str]


@dataclass(slots=True)
class ImportRuntime:
    category: Category
    definitions: dict[str, AttributeDefinition]
    brands: dict[str, Brand]
    products_by_sku: dict[str, Product]
    products_by_web_id: dict[str, Product]
    web_id_owners: dict[str, int]
    facets: dict[tuple[int, int], ProductAttributeValue]


def build_runtime(db: Session, config: CategoryConfig) -> ImportRuntime:
    category = db.scalar(select(Category).where(Category.code == config.code))
    if category is None:
        raise ValueError(f"Category chưa được seed: {config.code}")
    definitions = {
        item.attribute_key: item
        for item in db.scalars(
            select(AttributeDefinition).where(AttributeDefinition.category_id == category.id)
        )
    }
    products = list(
        db.scalars(
            select(Product)
            .where(Product.category_id == category.id)
            .options(
                joinedload(Product.specs),
                joinedload(Product.price),
                joinedload(Product.inventory),
                joinedload(Product.promotion),
                joinedload(Product.offers),
            )
        ).unique()
    )
    facets = {
        (item.product_id, item.attribute_id): item
        for item in db.scalars(
            select(ProductAttributeValue)
            .join(AttributeDefinition)
            .where(AttributeDefinition.category_id == category.id)
        )
    }
    return ImportRuntime(
        category=category,
        definitions=definitions,
        brands={item.normalized_name: item for item in db.scalars(select(Brand))},
        products_by_sku={item.sku: item for item in products},
        products_by_web_id={
            item.product_web_id: item for item in products if item.product_web_id
        },
        web_id_owners={
            web_id: product_id
            for product_id, web_id in db.execute(
                select(Product.id, Product.product_web_id).where(Product.product_web_id.is_not(None))
            )
            if web_id
        },
        facets=facets,
    )


def normalize_column_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_name = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_name = ascii_name.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_name)).strip("_")


def read_csv(file_path: Path, limit: int | None = None) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            frame = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=None,
                engine="python",
                dtype=object,
                nrows=limit,
            )
            frame.columns = [normalize_column_name(column) for column in frame.columns]
            return frame.where(pd.notna(frame), None)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ValueError(f"Không thể đọc CSV {file_path}: {last_error}")


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _set_path(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = target
    for part in path[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[path[-1]] = _json_value(value)


def normalize_product_row(row: dict[str, Any], config: CategoryConfig) -> NormalizedRow:
    raw_specs = {
        key: _json_value(normalize_empty_value(value))
        for key, value in row.items()
        if key not in COMMON_COLUMNS and normalize_empty_value(value) is not None
    }
    normalized_specs: dict[str, Any] = {}
    typed_values: dict[str, tuple[AttributeConfig, Any, str]] = {}
    warnings: list[str] = []
    for attribute in config.attributes:
        if not attribute.source_column:
            continue
        raw_value = row.get(attribute.source_column)
        if normalize_empty_value(raw_value) is None:
            continue
        try:
            parsed = attribute.parser(raw_value)
        except (ValueError, TypeError, ArithmeticError) as exc:
            parsed = None
            warnings.append(f"{attribute.key}: {exc}")
        if parsed is None:
            warnings.append(f"{attribute.key}: không parse được '{raw_value}'")
            continue
        _set_path(normalized_specs, attribute.normalized_path, parsed)
        typed_values[attribute.key] = (attribute, parsed, str(raw_value).strip())
    return NormalizedRow(raw_specs, normalized_specs, typed_values, warnings)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_value = ascii_value.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def _gifts(value: Any) -> list[dict[str, str]]:
    result = []
    for item in parse_list(value) or []:
        gift_type = "installment" if "trả góp" in item.casefold() else "gift"
        result.append({"type": gift_type, "name": item})
    return result


def _get_brand(
    db: Session, runtime: ImportRuntime, value: Any, source_brand_id: Any
) -> Brand | None:
    normalized = normalize_brand(value)
    if normalized is None:
        return None
    canonical, normalized_name = normalized
    brand = runtime.brands.get(normalized_name)
    if brand is None:
        brand = Brand(
            name=canonical,
            normalized_name=normalized_name,
            source_brand_id=normalize_text(source_brand_id),
        )
        db.add(brand)
        db.flush()
        runtime.brands[normalized_name] = brand
    elif brand.source_brand_id is None:
        brand.source_brand_id = normalize_text(source_brand_id)
    return brand


def _typed_columns(value: Any, data_type: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "value_text": None,
        "value_number": None,
        "value_boolean": None,
        "value_json": None,
    }
    if data_type == "number":
        result["value_number"] = value
    elif data_type == "boolean":
        result["value_boolean"] = value
    elif data_type == "text":
        result["value_text"] = str(value)
    else:
        result["value_json"] = _json_value(value)
    return result


def _upsert_offer(
    db: Session,
    product: Product,
    original_price: Decimal | None,
    sale_price: Decimal | None,
    gifts: list[dict[str, str]],
) -> None:
    if original_price is None and sale_price is not None:
        original_price = sale_price
    if sale_price is None and original_price is not None:
        sale_price = original_price
    if original_price is not None and sale_price is not None and sale_price > original_price:
        original_price = sale_price
    current = next((offer for offer in product.offers if offer.is_current), None)
    if current and (
        current.original_price == original_price
        and current.sale_price == sale_price
        and current.gifts == gifts
    ):
        return
    if current:
        current.is_current = False
        current.valid_to = datetime.now(UTC)
    product.offers.append(
        ProductOffer(
            product_id=product.id,
            original_price=original_price,
            sale_price=sale_price,
            gifts=gifts,
            is_current=True,
            valid_from=datetime.now(UTC),
        )
    )


def upsert_product(
    db: Session,
    row: dict[str, Any],
    config: CategoryConfig,
    options: ImportOptions,
    runtime: ImportRuntime | None = None,
) -> tuple[Product, NormalizedRow, bool]:
    runtime = runtime or build_runtime(db, config)
    category = runtime.category
    sku = normalize_text(row.get("sku"))
    product_web_id = normalize_text(row.get("productidweb"))
    if not sku and not product_web_id:
        raise ValueError("Thiếu cả sku và productidweb")
    product = (
        runtime.products_by_sku.get(sku)
        if sku
        else runtime.products_by_web_id.get(product_web_id or "")
    )
    existed = product is not None
    if product is not None and options.skip_existing:
        return product, normalize_product_row(row, config), True
    if existed and not options.update_existing:
        raise ValueError(f"Product đã tồn tại: {sku or product_web_id}")

    reliable_sku = sku or f"web:{product_web_id}"
    brand = _get_brand(db, runtime, row.get("brand"), row.get("brand_id"))
    brand_name = brand.name if brand else "Chưa xác định"
    model_code = normalize_text(row.get("model_code"))
    display_name = " ".join(item for item in (config.name, brand_name, model_code or reliable_sku) if item)
    normalized = normalize_product_row(row, config)

    if product is None:
        product = Product(
            sku=reliable_sku,
            slug=f"{config.slug}-{_slugify(brand_name)}-{_slugify(model_code or reliable_sku)}-{_slugify(reliable_sku)}",
            name=display_name,
            display_name=display_name,
            brand=brand_name,
            category=category,
            short_description=f"{display_name} từ catalog sản phẩm thực tế.",
            image_url="",
            featured=False,
            rating=0,
            review_count=0,
            source_data={},
        )
        db.add(product)
        db.flush()
        runtime.products_by_sku[reliable_sku] = product
    owner_id = runtime.web_id_owners.get(product_web_id or "")
    duplicate_web_id = owner_id is not None and owner_id != product.id
    product.product_web_id = None if duplicate_web_id else product_web_id
    if product.product_web_id:
        runtime.products_by_web_id[product.product_web_id] = product
        runtime.web_id_owners[product.product_web_id] = product.id
    product.model_code = model_code
    product.category = category
    product.brand_entity = brand
    product.brand = brand_name
    product.display_name = display_name
    product.name = display_name
    product.status = "active"
    product.source_data = {
        "category_code": config.code,
        "raw_product_web_id": product_web_id,
    }

    if product.specs is None:
        product.specs = ProductSpec()
    product.specs.raw_specs = normalized.raw_specs
    product.specs.normalized_specs = normalized.normalized_specs
    product.specs.search_text = " ".join(
        [display_name, *[str(value) for value in normalized.raw_specs.values()]]
    )
    product.specs.capacity_btu = int(
        normalized.typed_values.get("capacity_btu", (None, 0, ""))[1] or 0
    )
    product.specs.recommended_area_min = int(
        normalized.typed_values.get("recommended_area_min_m2", (None, 0, ""))[1] or 0
    )
    product.specs.recommended_area_max = int(
        normalized.typed_values.get("recommended_area_max_m2", (None, 0, ""))[1] or 0
    )
    product.specs.inverter = bool(
        normalized.typed_values.get("inverter", (None, False, ""))[1]
    )
    product.specs.horsepower = round(product.specs.capacity_btu / 9000, 1) if product.specs.capacity_btu else 0
    product.specs.noise_db = (
        float(normalized.typed_values["noise_db"][1])
        if "noise_db" in normalized.typed_values
        else None
    )
    product.specs.energy_rating = str(
        normalized.typed_values.get("energy_rating", (None, "Chưa có dữ liệu", ""))[1]
    )
    product.specs.warranty_months = int(
        normalized.typed_values.get("compressor_warranty_months", (None, 0, ""))[1] or 0
    )

    original_price = parse_price(row.get("gia_goc"))
    sale_price = parse_price(row.get("gia_khuyen_mai"))
    gifts = _gifts(row.get("khuyen_mai_qua"))
    _upsert_offer(db, product, original_price, sale_price, gifts)

    # Transitional compatibility rows for the current storefront.
    if product.price is None:
        product.price = Price(currency="VND")
    product.price.original_price = original_price or sale_price or Decimal(0)
    product.price.sale_price = sale_price or original_price or Decimal(0)
    if product.inventory is None:
        product.inventory = Inventory(stock_status="unknown", stock_quantity=0)
    if gifts:
        if product.promotion is None:
            product.promotion = Promotion()
        product.promotion.title = "Ưu đãi kèm sản phẩm"
        product.promotion.description = "; ".join(item["name"] for item in gifts)
    elif product.promotion is not None:
        product.promotion = None

    for key, (attribute, parsed, raw_value) in normalized.typed_values.items():
        definition = runtime.definitions.get(key)
        if definition is None:
            continue
        facet_key = (product.id, definition.id)
        facet = runtime.facets.get(facet_key)
        if facet is None:
            facet = ProductAttributeValue(product_id=product.id, attribute_id=definition.id)
            db.add(facet)
            runtime.facets[facet_key] = facet
        facet.raw_value = raw_value
        facet.unit = attribute.unit
        for column, value in _typed_columns(parsed, attribute.data_type).items():
            setattr(facet, column, value)
    return product, normalized, False


def import_file(
    file_path: Path, config: CategoryConfig, options: ImportOptions
) -> ImportReport:
    frame = read_csv(file_path, options.limit)
    records = [
        {key: _json_value(normalize_empty_value(value)) for key, value in record.items()}
        for record in frame.to_dict(orient="records")
    ]
    report = ImportReport(file_path.name, config.code, total_rows=len(records))
    if options.dry_run:
        for record in records:
            normalized = normalize_product_row(record, config)
            report.warnings += len(normalized.warnings)
            if normalize_text(record.get("sku")) or normalize_text(record.get("productidweb")):
                report.success_rows += 1
            else:
                report.failed_rows += 1
        return report

    checksum = hashlib.sha256(file_path.read_bytes()).hexdigest()
    with SessionLocal() as db:
        expected_attributes = sum(
            len(category.attributes) for category in CATEGORY_REGISTRY.values()
        )
        category_count = db.scalar(select(func.count()).select_from(Category)) or 0
        attribute_count = db.scalar(select(func.count()).select_from(AttributeDefinition)) or 0
        if category_count < len(CATEGORY_REGISTRY) or attribute_count < expected_attributes:
            seed_catalog_metadata(db)
        batch = ImportBatch(
            source_file=str(file_path),
            category_code=config.code,
            checksum=checksum,
            status="processing",
            total_rows=len(records),
            started_at=datetime.now(UTC),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        runtime = build_runtime(db, config)

        for offset in range(0, len(records), options.batch_size):
            chunk = records[offset : offset + options.batch_size]
            counters = (
                report.success_rows,
                report.failed_rows,
                report.skipped_rows,
                report.warnings,
            )
            try:
                for index, record in enumerate(chunk, start=offset + 1):
                    raw_row = RawProductRow(
                        batch_id=batch.id,
                        row_number=index,
                        raw_data=record,
                        import_status="processing",
                    )
                    db.add(raw_row)
                    try:
                        product, normalized, skipped = upsert_product(
                            db, record, config, options, runtime
                        )
                        raw_row.product_id = product.id
                        raw_row.import_status = "skipped" if skipped else "imported"
                        report.skipped_rows += int(skipped)
                        report.warnings += len(normalized.warnings)
                        report.success_rows += 1
                        for warning in normalized.warnings:
                            logger.warning("file=%s row=%d %s", file_path.name, index, warning)
                    except (ValueError, TypeError, ArithmeticError) as exc:
                        raw_row.import_status = "failed"
                        raw_row.error_message = str(exc)[:4000]
                        report.failed_rows += 1
                        logger.warning("file=%s row=%d import failed: %s", file_path.name, index, exc)
                        if options.fail_fast:
                            raise
                db.commit()
            except Exception:
                # A database-level failure invalidates the transaction. Roll the
                # chunk back, then isolate rows with savepoints so later rows continue.
                db.rollback()
                (
                    report.success_rows,
                    report.failed_rows,
                    report.skipped_rows,
                    report.warnings,
                ) = counters
                if options.fail_fast:
                    batch.status = "failed"
                    batch.completed_at = datetime.now(UTC)
                    db.commit()
                    raise
                runtime = build_runtime(db, config)
                logger.exception("Batch failed; retrying rows individually")
                for index, record in enumerate(chunk, start=offset + 1):
                    raw_row = RawProductRow(
                        batch_id=batch.id,
                        row_number=index,
                        raw_data=record,
                        import_status="processing",
                    )
                    db.add(raw_row)
                    try:
                        with db.begin_nested():
                            product, normalized, skipped = upsert_product(
                                db, record, config, options, runtime
                            )
                        raw_row.product_id = product.id
                        raw_row.import_status = "skipped" if skipped else "imported"
                        report.success_rows += 1
                        report.skipped_rows += int(skipped)
                        report.warnings += len(normalized.warnings)
                    except Exception as exc:
                        raw_row.import_status = "failed"
                        raw_row.error_message = str(exc)[:4000]
                        report.failed_rows += 1
                        logger.exception("file=%s row=%d import failed", file_path.name, index)
                        if options.fail_fast:
                            raise
                db.commit()

        completed_batch = db.get(ImportBatch, batch.id)
        if completed_batch is None:
            raise RuntimeError("Import batch disappeared")
        completed_batch.success_rows = report.success_rows
        completed_batch.failed_rows = report.failed_rows
        completed_batch.status = "completed_with_errors" if report.failed_rows else "completed"
        completed_batch.completed_at = datetime.now(UTC)
        db.commit()
    return report


def import_directory(directory: Path, options: ImportOptions) -> list[ImportReport]:
    reports: list[ImportReport] = []
    for file_path in sorted(directory.glob("*.csv")):
        config = category_for_file(file_path.name)
        if config is None:
            logger.warning("Bỏ qua file chưa có category mapping: %s", file_path)
            continue
        try:
            reports.append(import_file(file_path, config, options))
        except Exception:
            logger.exception("Import file thất bại: %s", file_path)
            if options.fail_fast:
                raise
    return reports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import catalog CSV vào hybrid PostgreSQL schema")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--directory", type=Path)
    parser.add_argument("--category", choices=sorted(CATEGORY_REGISTRY))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=300)
    strategy = parser.add_mutually_exclusive_group()
    strategy.add_argument("--update-existing", action="store_true")
    strategy.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parser().parse_args()
    if args.batch_size < 1 or args.batch_size > 5000:
        raise SystemExit("--batch-size phải nằm trong khoảng 1..5000")
    options = ImportOptions(
        dry_run=args.dry_run,
        limit=args.limit,
        batch_size=args.batch_size,
        update_existing=not args.skip_existing,
        skip_existing=args.skip_existing,
        fail_fast=args.fail_fast,
    )
    if args.file:
        config = CATEGORY_REGISTRY.get(args.category) if args.category else category_for_file(args.file.name)
        if config is None:
            raise SystemExit("Không xác định được category; hãy truyền --category")
        reports = [import_file(args.file, config, options)]
    else:
        reports = import_directory(args.directory, options)
    for report in reports:
        print(
            f"{report.category_code}: total={report.total_rows} success={report.success_rows} "
            f"failed={report.failed_rows} skipped={report.skipped_rows} warnings={report.warnings}"
        )
    if any(report.failed_rows for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
