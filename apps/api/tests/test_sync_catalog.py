from decimal import Decimal

from src.seed.sync_catalog_products import _mapped_values


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
