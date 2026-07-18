from decimal import Decimal

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from src.core.database import Base
from src.models import Category, Product
from src.seed.sync_catalog_products import (
    CATALOG_CATEGORIES,
    _map_row,
    _mapped_values,
    sync_catalog_products,
)


def test_maps_real_air_conditioner_fields_without_inventing_missing_data() -> None:
    values = _mapped_values(
        {
            "id": 1,
            "sku": "1751098000210",
            "model_code": "180706",
            "brand": "Panasonic",
            "gia_goc": Decimal("29490000"),
            "gia_khuyen_mai": None,
            "loai_may": "Máy lạnh 1 chiều",
            "pham_vi_su_dung": "Từ 30 - 40m² (từ 80 đến 120m³)",
            "cong_suat_dau_ra": "9.000 BTU",
            "loai_inverter": "Máy lạnh Inverter",
            "do_on": "Dàn lạnh: 45/34/29 dB - Dàn nóng: 51 dB",
            "nhan_nang_luong": "5 sao",
            "bao_hanh_bo_phan": "2 năm",
            "khuyen_mai_qua": "Phiếu mua hàng",
        }
    )

    assert values["name"] == "Máy lạnh Panasonic 180706"
    assert values["slug"] == "may-lanh-panasonic-180706-1751098000210"
    assert values["original_price"] == Decimal("29490000")
    assert values["sale_price"] == Decimal("29490000")
    assert values["capacity_btu"] == 9000
    assert values["horsepower"] == 1.0
    assert (values["recommended_area_min"], values["recommended_area_max"]) == (30, 40)
    assert values["inverter"] is True
    assert values["noise_db"] == 29
    assert values["warranty_months"] == 24


def test_missing_price_and_specs_remain_explicitly_unknown() -> None:
    values = _mapped_values(
        {
            "id": 2,
            "sku": "SKU-2",
            "model_code": "MODEL-2",
            "brand": "Test",
            "gia_goc": None,
            "gia_khuyen_mai": None,
        }
    )

    assert values["original_price"] == 0
    assert values["sale_price"] == 0
    assert values["capacity_btu"] == 0
    assert values["recommended_area_max"] == 0
    assert values["noise_db"] is None
    assert values["warranty_months"] == 0
    assert values["image_url"] == ""
    assert values["rating"] == 0


def test_maps_generic_category_and_preserves_specific_attributes() -> None:
    values = _map_row(
        {
            "id": 9,
            "sku": "TABLET-9",
            "model_code": "TAB-X",
            "brand": "Samsung",
            "gia_goc": Decimal("12000000"),
            "gia_khuyen_mai": Decimal("11000000"),
            "ram": "8 GB",
            "dung_luong_luu_tru": "256 GB",
        },
        CATALOG_CATEGORIES[-1],
    )

    assert values["name"] == "Máy tính bảng Samsung TAB-X"
    assert values["slug"] == "may-tinh-bang-samsung-tab-x-tablet-9"
    assert values["specifications"] == {"ram": "8 GB", "dung_luong_luu_tru": "256 GB"}
    assert values["capacity_btu"] == 0
    assert values["recommended_area_max"] == 0


def test_sync_multiple_raw_categories_into_api_read_model() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE refrigerators ("
                "id INTEGER PRIMARY KEY, sku TEXT, model_code TEXT, brand TEXT, "
                "gia_goc NUMERIC, gia_khuyen_mai NUMERIC, dung_tich_tong TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO refrigerators VALUES "
                "(1, 'FRIDGE-1', 'R100', 'LG', 10000000, 9000000, '500 lít')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE air_conditioners ("
                "id INTEGER PRIMARY KEY, sku TEXT, model_code TEXT, brand TEXT, "
                "gia_goc NUMERIC, gia_khuyen_mai NUMERIC, cong_suat_dau_ra TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO air_conditioners VALUES "
                "(1, 'AC-1', 'A100', 'Daikin', 12000000, 11000000, '9.000 BTU')"
            )
        )

    with Session(engine) as db:
        result = sync_catalog_products(db, CATALOG_CATEGORIES[:2])
        assert result.source_rows == 2
        assert result.categories == 2
        assert db.scalar(select(func.count()).select_from(Category)) == 2
        assert db.scalar(select(func.count()).select_from(Product)) == 2
        refrigerator = db.scalar(select(Product).where(Product.sku == "FRIDGE-1"))
        assert refrigerator is not None
        assert refrigerator.category.slug == "tu-lanh"
        assert refrigerator.specs.raw_specs["dung_tich_tong"] == "500 lít"
