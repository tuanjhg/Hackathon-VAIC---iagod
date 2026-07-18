from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

EMPTY_VALUES = {
    "",
    "-",
    "n/a",
    "đang cập nhật",
    "không có thông tin",
    "null",
    "none",
    "nan",
}


def normalize_text(value: Any) -> str | None:
    value = normalize_empty_value(value)
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_empty_value(value: Any) -> Any | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.casefold() in EMPTY_VALUES else value


def normalize_brand(value: Any) -> tuple[str, str] | None:
    name = normalize_text(value)
    if not name:
        return None
    canonical = re.sub(r"\s+(việt nam|viet nam|vietnam)$", "", name, flags=re.I).strip()
    decomposed = unicodedata.normalize("NFKD", canonical)
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    ascii_name = ascii_name.replace("đ", "d").replace("Đ", "D")
    normalized = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    return canonical, normalized


def _number_token(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    match = re.search(r"[-+]?\d[\d.,]*", text)
    return match.group(0) if match else None


def parse_decimal(value: Any) -> Decimal | None:
    token = _number_token(value)
    if token is None:
        return None
    token = token.replace(" ", "")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif token.count(".") > 1:
        token = token.replace(".", "")
    elif token.count(",") > 1:
        token = token.replace(",", "")
    elif "," in token:
        fraction = token.rsplit(",", 1)[1]
        token = token.replace(",", "." if len(fraction) <= 2 else "")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def parse_integer(value: Any) -> int | None:
    number = parse_decimal(value)
    return int(number) if number is not None else None


def parse_price(value: Any) -> Decimal | None:
    text = normalize_text(value)
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return Decimal(digits) if digits else None


def parse_boolean(value: Any) -> bool | None:
    text = normalize_text(value)
    if text is None:
        return None
    normalized = text.casefold()
    if any(token in normalized for token in ("không công bố", "chưa có", "đang cập nhật")):
        return None
    false_tokens = ("không", "no", "false", "0", "không hỗ trợ", "không có")
    true_tokens = ("có", "yes", "true", "1", "hỗ trợ", "inverter")
    if normalized in false_tokens or normalized.startswith("không "):
        return False
    if normalized in true_tokens or normalized.startswith("có "):
        return True
    # Feature columns often contain the concrete capability instead of "Có",
    # for example eSIM, GPS/GLONASS or Wi-Fi 6.
    return True


def parse_capacity_btu(value: Any) -> Decimal | None:
    text = normalize_text(value)
    if not text or "btu" not in text.casefold():
        return parse_decimal(value)
    match = re.search(r"\d[\d.,]*", text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return Decimal(digits) if digits else None


def parse_duration_months(value: Any) -> Decimal | None:
    number = parse_decimal(value)
    text = normalize_text(value)
    if number is None or not text:
        return None
    return number * 12 if "năm" in text.casefold() else number


def parse_duration_hours(value: Any) -> Decimal | None:
    number = parse_decimal(value)
    text = normalize_text(value)
    if number is None or not text:
        return None
    lowered = text.casefold()
    if "ngày" in lowered:
        return number * 24
    if "phút" in lowered:
        return number / 60
    return number


def parse_duration_minutes(value: Any) -> Decimal | None:
    number = parse_decimal(value)
    text = normalize_text(value)
    if number is None or not text:
        return None
    lowered = text.casefold()
    if "giờ" in lowered or "hour" in lowered:
        return number * 60
    return number


def parse_measurement(
    value: Any, target_unit: str, factors: dict[str, Decimal]
) -> Decimal | None:
    number = parse_decimal(value)
    text = normalize_text(value)
    if number is None or text is None:
        return None
    normalized = text.casefold().replace("²", "2")
    for unit in sorted(factors, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(unit)}(?![a-z])", normalized):
            return number * factors[unit]
    return number if target_unit else None


def parse_dimension(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "mm",
        {"mm": Decimal("1"), "cm": Decimal("10"), "m": Decimal("1000")},
    )


def parse_capacity_liter(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "liter",
        {"lít": Decimal("1"), "lit": Decimal("1"), "l": Decimal("1")},
    )


def parse_weight_kg(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "kg",
        {"kg": Decimal("1"), "g": Decimal("0.001")},
    )


def parse_weight_g(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "g",
        {"kg": Decimal("1000"), "g": Decimal("1")},
    )


def parse_power_watt(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "watt",
        {"kw": Decimal("1000"), "w": Decimal("1")},
    )


def parse_energy_kwh(value: Any) -> Decimal | None:
    return parse_measurement(value, "kwh", {"kwh": Decimal("1"), "wh": Decimal("0.001")})


def parse_screen_size_inch(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "inch",
        {"inch": Decimal("1"), '"': Decimal("1")},
    )


def parse_storage_gb(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "gb",
        {"tb": Decimal("1024"), "gb": Decimal("1"), "mb": Decimal("0.0009765625")},
    )


def parse_memory_gb(value: Any) -> Decimal | None:
    return parse_storage_gb(value)


def parse_area_m2(value: Any) -> Decimal | None:
    return parse_measurement(
        value,
        "m2",
        {"m2": Decimal("1"), "m²": Decimal("1")},
    )


def parse_range(value: Any) -> tuple[Decimal, Decimal] | None:
    text = normalize_text(value)
    if not text:
        return None
    numbers = [Decimal(item.replace(",", ".")) for item in re.findall(r"\d+(?:[.,]\d+)?", text)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        if "dưới" in text.casefold():
            return Decimal(0), numbers[0]
        return numbers[0], numbers[0]
    return None


def parse_range_min(value: Any) -> Decimal | None:
    parsed = parse_range(value)
    return parsed[0] if parsed else None


def parse_range_max(value: Any) -> Decimal | None:
    parsed = parse_range(value)
    return parsed[1] if parsed else None


def parse_list(value: Any) -> list[str] | None:
    text = normalize_text(value)
    if not text:
        return None
    items = [item.strip(" -•\t") for item in re.split(r"[;,\n]+", text)]
    result = list(dict.fromkeys(item for item in items if item))
    return result or None


def parse_list_count(value: Any) -> int | None:
    parsed = parse_list(value)
    return len(parsed) if parsed else None


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: normalize_empty_value(value) for key, value in record.items()}
