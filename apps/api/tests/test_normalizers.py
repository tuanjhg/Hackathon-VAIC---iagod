from decimal import Decimal

from src.importers.normalizers.common import (
    normalize_brand,
    normalize_empty_value,
    parse_area_m2,
    parse_boolean,
    parse_capacity_btu,
    parse_capacity_liter,
    parse_dimension,
    parse_list,
    parse_price,
    parse_range,
    parse_weight_kg,
)


def test_parse_vietnamese_price() -> None:
    assert parse_price("12.990.000 ₫") == Decimal("12990000")
    assert parse_price("1,250,000 VND") == Decimal("1250000")


def test_parse_measurements_and_range() -> None:
    assert parse_capacity_liter("406 lít") == Decimal("406")
    assert parse_dimension("171,5 cm") == Decimal("1715.0")
    assert parse_weight_kg("850 g") == Decimal("0.850")
    assert parse_area_m2("30 m²") == Decimal("30")
    assert parse_range("3 - 4 người") == (Decimal("3"), Decimal("4"))


def test_parse_boolean_list_brand_and_empty_values() -> None:
    assert parse_boolean("Có") is True
    assert parse_boolean("Không") is False
    assert parse_boolean("eSIM") is True
    assert parse_boolean("Hãng không công bố") is None
    assert parse_capacity_btu("9.000 BTU") == Decimal("9000")
    assert parse_list("Wi-Fi; Bluetooth, GPS") == ["Wi-Fi", "Bluetooth", "GPS"]
    assert normalize_brand("Samsung Việt Nam") == ("Samsung", "samsung")
    assert normalize_brand("SAMSUNG") == ("SAMSUNG", "samsung")
    assert normalize_empty_value("Đang cập nhật") is None
    assert normalize_empty_value("") is None
