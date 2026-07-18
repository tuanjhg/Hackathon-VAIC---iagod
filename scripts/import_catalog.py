#!/usr/bin/env python3
"""Import the 14 product catalog CSV files into separate PostgreSQL tables.

The importer is idempotent in append mode: a SHA-256 hash of every normalized
source record is protected by a unique PostgreSQL index.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "realdata" / "raw" / "clean"
LOG_FILE = PROJECT_ROOT / "logs" / "import_catalog.log"
DEFAULT_BATCH_SIZE = 500

SYSTEM_COLUMNS = {
    "id",
    "source_row_id",
    "category_name",
    "source_file",
    "data_hash",
    "created_at",
    "updated_at",
}

SQL_KEYWORDS = {
    "all", "analyse", "analyze", "and", "any", "array", "as", "asc",
    "asymmetric", "authorization", "binary", "both", "case", "cast",
    "check", "collate", "column", "constraint", "create", "current_date",
    "current_role", "current_time", "current_timestamp", "current_user",
    "default", "deferrable", "desc", "distinct", "do", "else", "end",
    "except", "false", "for", "foreign", "freeze", "from", "full",
    "grant", "group", "having", "ilike", "in", "initially", "inner",
    "intersect", "into", "is", "isnull", "join", "leading", "left",
    "like", "limit", "localtime", "localtimestamp", "natural", "new",
    "not", "notnull", "null", "off", "offset", "old", "on", "only",
    "or", "order", "outer", "overlaps", "placing", "primary", "references",
    "right", "select", "session_user", "similar", "some", "symmetric",
    "table", "then", "to", "trailing", "true", "union", "unique", "user",
    "using", "verbose", "when", "where", "window", "with",
}

NULL_STRINGS = {"", "null", "none", "n/a", "nan"}
ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "windows-1252")
DELIMITERS = (",", ";", "\t")


@dataclass(frozen=True)
class CategoryConfig:
    """Static mapping between a catalog category, CSV file, and DB table."""

    category_name: str
    table_name: str
    file_name: str
    expected_rows: int


CATEGORIES: tuple[CategoryConfig, ...] = (
    CategoryConfig("Tủ Lạnh", "refrigerators", "tu_lanh.csv", 1692),
    CategoryConfig("Máy lạnh", "air_conditioners", "may_lanh.csv", 1039),
    CategoryConfig("Máy giặt", "washing_machines", "may_giat.csv", 1337),
    CategoryConfig("Máy sấy quần áo", "clothes_dryers", "may_say.csv", 107),
    CategoryConfig("Máy rửa chén", "dishwashers", "may_rua_chen.csv", 134),
    CategoryConfig("Tủ mát, tủ đông", "coolers_freezers", "tu_mat_dong.csv", 222),
    CategoryConfig("Máy nước nóng", "water_heaters", "may_nuoc_nong.csv", 319),
    CategoryConfig("Micro karaoke", "karaoke_microphones", "micro_karaoke.csv", 37),
    CategoryConfig(
        "Micro thu âm điện thoại",
        "phone_recording_microphones",
        "micro_thu_am.csv",
        33,
    ),
    CategoryConfig("Đồng hồ thông minh", "smartwatches", "dong_ho_tm.csv", 1336),
    CategoryConfig("Máy tính để bàn", "desktop_computers", "pc_de_ban.csv", 405),
    CategoryConfig("Màn hình máy tính", "computer_monitors", "man_hinh.csv", 469),
    CategoryConfig("Máy in", "printers", "may_in.csv", 147),
    CategoryConfig("Máy tính bảng", "tablets", "may_tinh_bang.csv", 1469),
)


@dataclass
class ImportResult:
    """Metrics collected for one category import."""

    table_name: str
    expected: int
    csv_rows: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: int = 0
    db_total: int = 0
    status: str = "OK"
    warnings: list[str] = field(default_factory=list)


def normalize_column_name(column_name: str) -> str:
    """Return a safe, unaccented, lower-case PostgreSQL column name.

    Duplicate names are handled by :func:`normalize_dataframe_columns`, because
    uniqueness requires knowledge of all headers in a file.
    """

    value = str(column_name).strip().replace("\r", " ").replace("\n", " ")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("đ", "d").replace("Đ", "D").lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    if not value:
        value = "unnamed_column"
    if value[0].isdigit():
        value = f"col_{value}"
    if value in SQL_KEYWORDS:
        value = f"{value}_field"
    if value in SYSTEM_COLUMNS:
        value = f"csv_{value}"
    return value[:63].rstrip("_")


def normalize_dataframe_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Normalize and de-duplicate a DataFrame's columns."""

    used: set[str] = set()
    normalized: list[str] = []
    renamed: dict[str, str] = {}
    for original in df.columns:
        base = normalize_column_name(str(original))
        candidate = base
        suffix = 2
        while candidate in used:
            suffix_text = f"_{suffix}"
            candidate = f"{base[: 63 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        used.add(candidate)
        normalized.append(candidate)
        if str(original) != candidate:
            renamed[str(original)] = candidate
    result = df.copy()
    result.columns = normalized
    return result, renamed


def _read_with_encoding(file_path: Path, encoding: str) -> pd.DataFrame:
    """Decode and parse a CSV using a detected delimiter."""

    with file_path.open("r", encoding=encoding, newline="") as handle:
        sample = handle.read(64 * 1024)
    if not sample.strip():
        raise ValueError("File CSV rỗng")
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
    except csv.Error:
        delimiter = max(DELIMITERS, key=lambda item: sample.partition("\n")[0].count(item))
    if sample.partition("\n")[0].count(delimiter) == 0:
        raise ValueError("Không phát hiện được delimiter ',', ';' hoặc tab")
    return pd.read_csv(
        file_path,
        encoding=encoding,
        sep=delimiter,
        dtype=object,
        keep_default_na=False,
        na_filter=False,
        on_bad_lines="error",
    )


def read_csv_safely(file_path: str) -> pd.DataFrame:
    """Read a CSV with safe encoding/delimiter detection and normalized schema."""

    path = Path(file_path)
    errors: list[str] = []
    for encoding in ENCODINGS:
        try:
            frame = _read_with_encoding(path, encoding)
            frame, _ = normalize_dataframe_columns(frame)
            frame = frame.dropna(axis=1, how="all")
            empty_columns = [
                column
                for column in frame.columns
                if frame[column].map(lambda value: _normalize_scalar(value) is None).all()
            ]
            return frame.drop(columns=empty_columns)
        except (UnicodeDecodeError, UnicodeError, pd.errors.ParserError, ValueError) as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError(f"Không thể đọc CSV {path}: {'; '.join(errors)}")


def _normalize_scalar(value: Any) -> Any:
    """Normalize one scalar for hashing and database insertion."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        cleaned = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if cleaned.casefold() in NULL_STRINGS:
            return None
        return cleaned
    return value


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Normalize empty values and remove completely empty source rows."""

    cleaned = df.map(_normalize_scalar)
    empty_mask = cleaned.isna().all(axis=1)
    empty_count = int(empty_mask.sum())
    return cleaned.loc[~empty_mask].reset_index(drop=True), empty_count


def _has_leading_zero(value: str) -> bool:
    stripped = value.lstrip("+-")
    return len(stripped) > 1 and stripped.startswith("0") and not stripped.startswith("0.")


def _parse_money(value: str) -> Decimal | None:
    """Parse common Vietnamese/international money formats conservatively."""

    cleaned = re.sub(r"[^0-9,\.\-+]", "", value)
    if not cleaned or cleaned in {"-", "+"}:
        return None
    if "," in cleaned and "." in cleaned:
        decimal_mark = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_mark = "." if decimal_mark == "," else ","
        cleaned = cleaned.replace(thousands_mark, "").replace(decimal_mark, ".")
    elif re.fullmatch(r"[+-]?\d{1,3}([.,]\d{3})+", cleaned):
        cleaned = cleaned.replace(",", "").replace(".", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def infer_column_type(series: pd.Series, column_name: str) -> tuple[str, str]:
    """Infer a permissive PostgreSQL type and a conversion strategy."""

    values = [str(value).strip() for value in series.dropna().tolist()]
    if not values:
        return "TEXT", "text"

    folded = {value.casefold() for value in values}
    if folded <= {"true", "false", "yes", "no", "0", "1", "co", "khong", "có", "không"}:
        return "BOOLEAN", "bool"

    money_hint = bool(re.search(r"(^|_)(gia|price|amount|cost|tien)($|_)", column_name))
    parsed_money = [_parse_money(value) for value in values]
    if money_hint and all(value is not None for value in parsed_money):
        return "NUMERIC", "numeric"

    if all(re.fullmatch(r"[+-]?\d+", value) for value in values) and not any(
        _has_leading_zero(value) for value in values
    ):
        return "BIGINT", "integer"

    if all(value is not None for value in parsed_money) and any(
        "." in value or "," in value for value in values
    ):
        return "NUMERIC", "numeric"

    date_hint = bool(re.search(r"(^|_)(date|time|ngay|thoi_gian|timestamp)($|_)", column_name))
    if date_hint and len(values) >= 2:
        parsed_dates = pd.to_datetime(
            pd.Series(values), errors="coerce", utc=True, format="mixed", dayfirst=True
        )
        # One free-form value is enough to make a timestamp schema unsafe.
        # Prefer text over losing data or rolling back a whole category.
        if bool(parsed_dates.notna().all()):
            return "TIMESTAMPTZ", "datetime"

    max_length = max(len(value) for value in values)
    if max_length <= 255:
        # Keep headroom for future append runs instead of constraining the
        # schema to the longest value observed in the current file.
        return "VARCHAR(255)", "text"
    return "TEXT", "text"


def convert_value(value: Any, strategy: str) -> Any:
    """Convert a normalized value according to a safe inferred strategy."""

    if value is None:
        return None
    if strategy == "integer":
        return int(str(value))
    if strategy == "numeric":
        parsed = _parse_money(str(value))
        if parsed is None:
            raise ValueError(f"Giá trị NUMERIC không hợp lệ: {value!r}")
        return parsed
    if strategy == "bool":
        return str(value).casefold() in {"true", "yes", "1", "co", "có"}
    if strategy == "datetime":
        parsed = pd.to_datetime(
            value, errors="raise", utc=True, format="mixed", dayfirst=True
        )
        return parsed.to_pydatetime()
    return str(value)


def compute_data_hash(record: dict[str, Any]) -> str:
    """Compute a stable SHA-256 hash from normalized source data."""

    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_database_url() -> URL:
    """Build and validate a PostgreSQL URL without logging credentials."""

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        try:
            url = make_url(database_url)
        except Exception as exc:
            raise ValueError("DATABASE_URL không hợp lệ") from exc
        if not url.drivername.startswith("postgresql"):
            raise ValueError("DATABASE_URL phải sử dụng PostgreSQL")
        # This standalone importer uses psycopg2, including when the application
        # itself is configured with the SQLAlchemy psycopg (v3) dialect.
        return url.set(drivername="postgresql+psycopg2")

    names = (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise ValueError(
            "Thiếu cấu hình PostgreSQL trong .env: " + ", ".join(missing)
        )
    try:
        port = int(os.environ["POSTGRES_PORT"])
    except ValueError as exc:
        raise ValueError("POSTGRES_PORT phải là số nguyên") from exc
    if not 1 <= port <= 65535:
        raise ValueError("POSTGRES_PORT phải nằm trong khoảng 1..65535")
    return URL.create(
        "postgresql+psycopg2",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=port,
        database=os.environ["POSTGRES_DB"],
    )


def configure_logging() -> logging.Logger:
    """Configure UTF-8 console and rotating-by-run file logging."""

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("import_catalog")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def configure_utf8_stdio() -> None:
    """Use UTF-8 for Windows terminals and redirected output when supported."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def quote_identifier(connection: Connection, identifier: str) -> str:
    """Quote a trusted identifier using the active SQLAlchemy dialect."""

    return connection.dialect.identifier_preparer.quote(identifier)


def table_exists(connection: Connection, table_name: str) -> bool:
    """Return whether a table exists in the current PostgreSQL schema."""

    return inspect(connection).has_table(table_name)


def prepare_table(
    connection: Connection,
    config: CategoryConfig,
    column_types: dict[str, str],
    mode: str,
) -> None:
    """Create/evolve a category table and apply the requested data mode."""

    table = quote_identifier(connection, config.table_name)
    exists = table_exists(connection, config.table_name)
    if mode == "replace" and exists:
        connection.execute(text(f"DROP TABLE {table}"))
        exists = False

    dynamic_definitions = ",\n".join(
        f"{quote_identifier(connection, name)} {sql_type}"
        for name, sql_type in column_types.items()
    )
    comma_dynamic = f",\n{dynamic_definitions}" if dynamic_definitions else ""
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id BIGSERIAL PRIMARY KEY,
                source_row_id BIGINT,
                category_name VARCHAR(255) NOT NULL,
                source_file VARCHAR(500),
                data_hash VARCHAR(64),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
                {comma_dynamic}
            )
            """
        )
    )

    existing_columns = {item["name"] for item in inspect(connection).get_columns(config.table_name)}
    for name, sql_type in column_types.items():
        if name not in existing_columns:
            connection.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN "
                    f"{quote_identifier(connection, name)} {sql_type}"
                )
            )

    if mode == "truncate":
        connection.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY"))

    index_name = f"uq_{config.table_name}_data_hash"
    connection.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS "
            f"{quote_identifier(connection, index_name)} ON {table} (data_hash)"
        )
    )


def build_records(
    df: pd.DataFrame,
    config: CategoryConfig,
    strategies: dict[str, str],
) -> list[dict[str, Any]]:
    """Convert a DataFrame to insertion records including system metadata."""

    records: list[dict[str, Any]] = []
    for row_index, row in df.iterrows():
        normalized = {column: _normalize_scalar(row[column]) for column in df.columns}
        converted = {
            column: convert_value(value, strategies[column])
            for column, value in normalized.items()
        }
        records.append(
            {
                "source_row_id": row_index + 1,
                "category_name": config.category_name,
                "source_file": config.file_name,
                "data_hash": compute_data_hash(normalized),
                **converted,
            }
        )
    return records


def batched(items: Sequence[dict[str, Any]], size: int) -> Iterable[Sequence[dict[str, Any]]]:
    """Yield fixed-size batches."""

    for start in range(0, len(items), size):
        yield items[start : start + size]


def bulk_insert(
    connection: Connection,
    table_name: str,
    records: Sequence[dict[str, Any]],
    batch_size: int,
) -> int:
    """Bulk insert via psycopg2 execute_values with ON CONFLICT DO NOTHING."""

    if not records:
        return 0
    from psycopg2.extras import execute_values

    columns = list(records[0].keys())
    quoted_columns = ", ".join(quote_identifier(connection, item) for item in columns)
    table = quote_identifier(connection, table_name)
    sql = f"INSERT INTO {table} ({quoted_columns}) VALUES %s ON CONFLICT DO NOTHING"
    inserted = 0
    cursor = connection.connection.cursor()
    try:
        for batch in batched(records, batch_size):
            values = [tuple(record[column] for column in columns) for record in batch]
            execute_values(cursor, sql, values, page_size=batch_size)
            inserted += max(cursor.rowcount, 0)
    finally:
        cursor.close()
    return inserted


def resolve_csv_path(data_dir: Path, file_name: str) -> Path:
    """Resolve both a flat data directory and the repository clean layout."""

    candidates = (
        data_dir / file_name,
        data_dir / "realdata" / "raw" / "clean" / file_name,
        DEFAULT_DATA_DIR / file_name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def log_data_quality(
    logger: logging.Logger,
    config: CategoryConfig,
    frame: pd.DataFrame,
    renamed: dict[str, str],
    column_types: dict[str, str],
    empty_rows: int,
    duplicate_hashes: int,
) -> None:
    """Log the requested per-file data quality diagnostics."""

    total_before_empty = len(frame) + empty_rows
    empty_rate = empty_rows / total_before_empty if total_before_empty else 0.0
    null_rates = {
        column: round(float(frame[column].isna().mean()) * 100, 2)
        for column in frame.columns
        if frame[column].isna().any()
    }
    text_columns = [name for name, sql_type in column_types.items() if sql_type == "TEXT"]
    logger.info(
        "file=%s table=%s rows=%d empty_rows=%d empty_rate=%.2f%% duplicate_hashes=%d",
        config.file_name,
        config.table_name,
        len(frame),
        empty_rows,
        empty_rate * 100,
        duplicate_hashes,
    )
    logger.info("file=%s table=%s renamed_columns=%s", config.file_name, config.table_name, renamed)
    logger.info("file=%s table=%s text_columns=%s", config.file_name, config.table_name, text_columns)
    logger.info("file=%s table=%s null_rates_percent=%s", config.file_name, config.table_name, null_rates)


def import_category(
    engine: Engine,
    config: CategoryConfig,
    data_dir: Path,
    mode: str,
    batch_size: int,
    logger: logging.Logger,
) -> ImportResult:
    """Import one category in its own transaction; return metrics on all failures."""

    result = ImportResult(config.table_name, config.expected_rows)
    csv_path = resolve_csv_path(data_dir, config.file_name)
    if not csv_path.is_file():
        result.errors = 1
        result.status = "FILE MISSING"
        result.warnings.append(f"Không tìm thấy file: {csv_path}")
        logger.error("file=%s table=%s error=file_not_found path=%s", config.file_name, config.table_name, csv_path)
        return result

    try:
        raw_frame = _read_csv_with_metadata(csv_path)
        result.csv_rows = len(raw_frame[0])
        frame, renamed = normalize_dataframe_columns(raw_frame[0])
        frame, empty_rows = clean_dataframe(frame)
        empty_columns = [column for column in frame.columns if frame[column].isna().all()]
        frame = frame.drop(columns=empty_columns)
        if empty_columns:
            logger.warning("file=%s table=%s removed_empty_columns=%s", config.file_name, config.table_name, empty_columns)

        inferred = {column: infer_column_type(frame[column], column) for column in frame.columns}
        column_types = {column: value[0] for column, value in inferred.items()}
        strategies = {column: value[1] for column, value in inferred.items()}
        records = build_records(frame, config, strategies)
        hashes = [record["data_hash"] for record in records]
        duplicate_hashes = len(hashes) - len(set(hashes))
        log_data_quality(
            logger, config, frame, renamed, column_types, empty_rows, duplicate_hashes
        )

        with engine.begin() as connection:
            prepare_table(connection, config, column_types, mode)
            result.inserted = bulk_insert(connection, config.table_name, records, batch_size)
            result.skipped = len(records) - result.inserted
            table = quote_identifier(connection, config.table_name)
            result.db_total = int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())

        if result.csv_rows != config.expected_rows:
            result.warnings.append(
                f"CSV rows {result.csv_rows} != expected {config.expected_rows}"
            )
        if result.db_total != config.expected_rows:
            result.warnings.append(
                f"DB total {result.db_total} != expected {config.expected_rows}"
            )
        if empty_rows:
            result.warnings.append(f"Đã bỏ {empty_rows} dòng hoàn toàn rỗng")
        if duplicate_hashes:
            result.warnings.append(f"CSV có {duplicate_hashes} hash trùng")
        if result.warnings:
            result.status = "WARNING"
            for warning in result.warnings:
                logger.warning("file=%s table=%s warning=%s", config.file_name, config.table_name, warning)
        logger.info(
            "file=%s table=%s rows_read=%d inserted=%d skipped=%d errors=%d db_total=%d",
            config.file_name,
            config.table_name,
            result.csv_rows,
            result.inserted,
            result.skipped,
            result.errors,
            result.db_total,
        )
    except Exception as exc:
        result.errors = max(1, result.csv_rows)
        result.status = "FAILED"
        result.warnings.append(str(exc))
        logger.exception("file=%s table=%s import_failed: %s", config.file_name, config.table_name, exc)
    return result


def _read_csv_with_metadata(file_path: Path) -> tuple[pd.DataFrame, str, str]:
    """Read CSV while retaining the selected encoding and delimiter for logs."""

    errors: list[str] = []
    for encoding in ENCODINGS:
        try:
            with file_path.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(64 * 1024)
            if not sample.strip():
                raise ValueError("File CSV rỗng")
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters="".join(DELIMITERS)).delimiter
            except csv.Error:
                delimiter = max(DELIMITERS, key=lambda item: sample.partition("\n")[0].count(item))
            if sample.partition("\n")[0].count(delimiter) == 0:
                raise ValueError("Không phát hiện delimiter hợp lệ")
            frame = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=delimiter,
                dtype=object,
                keep_default_na=False,
                na_filter=False,
                on_bad_lines="error",
            )
            return frame, encoding, delimiter
        except (UnicodeDecodeError, UnicodeError, pd.errors.ParserError, ValueError) as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError(f"Không thể đọc CSV: {'; '.join(errors)}")


def print_report(results: Sequence[ImportResult]) -> None:
    """Print aligned per-table and total import metrics."""

    headers = ("Table", "Expected", "CSV rows", "Inserted", "Skipped", "Errors", "DB total", "Status")
    rows = [
        (
            item.table_name,
            item.expected,
            item.csv_rows,
            item.inserted,
            item.skipped,
            item.errors,
            item.db_total,
            item.status,
        )
        for item in results
    ]
    rows.append(
        (
            "TOTAL",
            sum(item.expected for item in results),
            sum(item.csv_rows for item in results),
            sum(item.inserted for item in results),
            sum(item.skipped for item in results),
            sum(item.errors for item in results),
            sum(item.db_total for item in results),
            "OK" if all(item.status == "OK" for item in results) else "CHECK LOG",
        )
    )
    widths = [
        max(len(str(header)), *(len(str(row[index])) for row in rows))
        for index, header in enumerate(headers)
    ]
    print("\n" + "  ".join(str(header).ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--category",
        choices=[item.table_name for item in CATEGORIES],
        help="Chỉ import một table",
    )
    selection.add_argument("--all", action="store_true", help="Import toàn bộ 14 table")
    parser.add_argument(
        "--mode",
        choices=("append", "replace", "truncate"),
        default="append",
        help="Cách xử lý table đã tồn tại (mặc định: append)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    configure_utf8_stdio()
    args = parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    logger = configure_logging()

    try:
        database_url = get_database_url()
        batch_size = int(os.getenv("IMPORT_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))
        if batch_size <= 0:
            raise ValueError("IMPORT_BATCH_SIZE phải lớn hơn 0")
    except ValueError as exc:
        logger.error("configuration_error=%s", exc)
        return 2

    raw_data_dir = os.getenv("CSV_DATA_DIR", "").strip()
    data_dir = (PROJECT_ROOT / raw_data_dir).resolve() if raw_data_dir and not Path(raw_data_dir).is_absolute() else Path(raw_data_dir or DEFAULT_DATA_DIR).resolve()
    selected = [item for item in CATEGORIES if not args.category or item.table_name == args.category]
    if not args.category and not args.all:
        logger.info("Không có --category/--all; mặc định import toàn bộ ở mode append")

    engine = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info(
            "Kết nối PostgreSQL thành công host=%s database=%s user=%s (password hidden)",
            database_url.host,
            database_url.database,
            database_url.username,
        )
    except SQLAlchemyError as exc:
        detail = getattr(exc, "orig", exc)
        logger.error(
            "Không thể kết nối PostgreSQL: %s: %s",
            exc.__class__.__name__,
            detail,
        )
        engine.dispose()
        return 2

    results: list[ImportResult] = []
    try:
        for config in selected:
            results.append(
                import_category(engine, config, data_dir, args.mode, batch_size, logger)
            )
    finally:
        engine.dispose()

    print_report(results)
    failed = any(item.status in {"FAILED", "FILE MISSING"} for item in results)
    mismatched = any(item.warnings for item in results)
    return 1 if failed or mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
