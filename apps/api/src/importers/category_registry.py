from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.importers.normalizers import common

Parser = Callable[[Any], Any | None]


@dataclass(frozen=True, slots=True)
class AttributeConfig:
    key: str
    source_column: str | None
    display_name: str
    data_type: str
    unit: str | None
    group_name: str
    parser: Parser
    normalized_path: tuple[str, ...]
    filterable: bool = True
    comparable: bool = True


@dataclass(frozen=True, slots=True)
class CategoryConfig:
    code: str
    name: str
    slug: str
    file_names: tuple[str, ...]
    attributes: tuple[AttributeConfig, ...]


CATEGORY_META = {
    "refrigerators": ("Tủ lạnh", "tu-lanh", ("tu_lanh.csv", "refrigerators.csv")),
    "air_conditioners": ("Máy lạnh", "may-lanh", ("may_lanh.csv", "air_conditioners.csv")),
    "washing_machines": ("Máy giặt", "may-giat", ("may_giat.csv", "washing_machines.csv")),
    "clothes_dryers": ("Máy sấy quần áo", "may-say-quan-ao", ("may_say.csv", "clothes_dryers.csv")),
    "dishwashers": ("Máy rửa chén", "may-rua-chen", ("may_rua_chen.csv", "dishwashers.csv")),
    "coolers_freezers": ("Tủ mát, tủ đông", "tu-mat-tu-dong", ("tu_mat_dong.csv", "coolers_freezers.csv")),
    "water_heaters": ("Máy nước nóng", "may-nuoc-nong", ("may_nuoc_nong.csv", "water_heaters.csv")),
    "karaoke_microphones": ("Micro karaoke", "micro-karaoke", ("micro_karaoke.csv", "karaoke_microphones.csv")),
    "phone_recording_microphones": ("Micro thu âm điện thoại", "micro-thu-am-dien-thoai", ("micro_thu_am.csv", "phone_recording_microphones.csv")),
    "smartwatches": ("Đồng hồ thông minh", "dong-ho-thong-minh", ("dong_ho_tm.csv", "smartwatches.csv")),
    "desktop_computers": ("Máy tính để bàn", "may-tinh-de-ban", ("pc_de_ban.csv", "desktop_computers.csv")),
    "computer_monitors": ("Màn hình máy tính", "man-hinh-may-tinh", ("man_hinh.csv", "computer_monitors.csv")),
    "printers": ("Máy in", "may-in", ("may_in.csv", "printers.csv")),
    "tablets": ("Máy tính bảng", "may-tinh-bang", ("may_tinh_bang.csv", "tablets.csv")),
}

# key -> source column. Keys without a reliable source remain seeded metadata but
# do not produce a typed value until a category override is added.
SOURCE_COLUMNS: dict[str, dict[str, str]] = {
    "refrigerators": {"total_capacity_liter":"dung_tich_tong","freezer_capacity_liter":"dung_tich_ngan_da","refrigerator_capacity_liter":"dung_tich_ngan_lanh","soft_freezer_capacity_liter":"dung_tich_ngan_chuyen_doi","recommended_users_min":"so_nguoi_su_dung","recommended_users_max":"so_nguoi_su_dung","door_count":"so_cua","energy_consumption_kwh_per_day":"dien_nang_tieu_thu","inverter":"cong_nghe_tiet_kiem_dien","has_external_water_dispenser":"lay_nuoc_ngoai","has_auto_ice":"che_do_tu_dong","height_mm":"cao","width_mm":"ngang","depth_mm":"sau","weight_kg":"khoi_luong_may"},
    "air_conditioners": {"capacity_btu":"cong_suat_dau_ra","recommended_area_min_m2":"pham_vi_su_dung","recommended_area_max_m2":"pham_vi_su_dung","inverter":"loai_inverter","energy_rating":"nhan_nang_luong","power_consumption_kw":"dien_nang_tieu_thu","noise_db":"do_on","gas_type":"loai_gas","cooling_mode":"loai_may","water_dust_standard":"chuan_chong_nuoc_bui","compressor_warranty_months":"bao_hanh_dong_co"},
    "washing_machines": {"washing_capacity_kg":"khoi_luong_tai_chinh","recommended_users_min":"so_nguoi_su_dung","recommended_users_max":"so_nguoi_su_dung","max_spin_speed_rpm":"toc_do_quay_vat_toi_da","inverter":"loai_inverter","dryer_supported":"cong_nghe_say","motor_type":"dong_co","height_mm":"cao","width_mm":"ngang","depth_mm":"sau","weight_kg":"khoi_luong_may"},
    "clothes_dryers": {"drying_capacity_kg":"khoi_luong_tai_chinh","dryer_technology":"cong_nghe_say","max_temperature_celsius":"nhiet_do_toi_da","energy_consumption_kwh":"dien_nang_tieu_thu","motor_type":"dong_co","sensor_features":"cam_bien","height_mm":"cao","width_mm":"ngang","depth_mm":"sau"},
    "dishwashers": {"place_settings":"so_luong","water_consumption_liter":"tieu_thu_nuoc","noise_db":"do_on","drying_technology":"cong_nghe_say","installation_type":"loai_san_pham","program_count":"chuong_trinh","height_mm":"cao","width_mm":"ngang","depth_mm":"sau"},
    "coolers_freezers": {"total_capacity_liter":"dung_tich_tong","door_count":"so_cua","compartment_count":"so_ngan","soft_freezer_capacity_liter":"dung_tich_ngan_dong_mem","freezer_temperature_celsius":"nhiet_do_ngan_dong_do_c","energy_consumption_kwh":"dien_nang_tieu_thu","inverter":"cong_nghe_tiet_kiem_dien","height_mm":"cao","width_mm":"ngang","depth_mm":"sau"},
    "water_heaters": {"capacity_liter":"dung_luong_dung_tich","power_watt":"cong_suat_dau_ra","max_temperature_celsius":"nhiet_do_lam_nong_toi_da","operating_water_pressure":"ap_luc_nuoc_hoat_dong","has_booster_pump":"bom_tro_luc","retention_time_hours":"thoi_gian_giu_nhiet","safety_features":"tinh_nang_an_toan","height_mm":"cao","width_mm":"rong","depth_mm":"day"},
    "karaoke_microphones": {"frequency_min_mhz":"tan_so_hoat_dong","frequency_max_mhz":"tan_so_hoat_dong","frequency_band":"bang_tan","distortion_percent":"do_meo_tieng","product_type":"loai_san_pham","manufacture_year":"nam_san_xuat"},
    "phone_recording_microphones": {"transmission_distance_meter":"khoang_cach_truyen","transmitter_battery_mah":"dung_luong_pin_bo_phat","receiver_battery_mah":"dung_luong_pin_bo_thu","charging_case_battery_mah":"dung_luong_pin_hop_sac","transmitter_runtime_hours":"thoi_gian_hoat_dong_bo_phat","receiver_runtime_hours":"thoi_gian_hoat_dong_bo_thu","frequency_min_mhz":"tan_so_hoat_dong","frequency_max_mhz":"tan_so_hoat_dong","sound_pressure_level_db":"ap_suat_am_thanh_spl","connection_types":"ket_noi","compatibility":"tuong_thich"},
    "smartwatches": {"screen_size_inch":"kich_thuoc_man_hinh","battery_capacity_mah":"dung_luong_pin","battery_life_hours":"thoi_gian_su_dung","charging_time_minutes":"thoi_gian_sac","water_resistance":"chuan_chong_nuoc_bui","gps":"dinh_vi","supports_sim":"sim","supports_calling":"thuc_hien_cuoc_goi","operating_system":"he_dieu_hanh","compatible_os":"tuong_thich","case_width_mm":"ngang","weight_g":"khoi_luong_may"},
    "desktop_computers": {"cpu_model":"loai_cpu","cpu_core_count":"so_nhan","cpu_base_clock_ghz":"toc_do_cpu","cpu_max_clock_ghz":"toc_do_toi_da","ram_gb":"ram","ram_type":"loai_ram","max_ram_gb":"ho_tro_ram_toi_da","storage_gb":"o_cung","storage_type":"chuan_ket_noi_o_cung","gpu_model":"model_gpu","gpu_memory_gb":"bo_nho","operating_system":"he_dieu_hanh","wifi":"wifi","power_supply_watt":"nguon_dien"},
    "computer_monitors": {"screen_size_inch":"kich_thuoc_man_hinh","resolution_width":"do_phan_giai","resolution_height":"do_phan_giai","panel_type":"tam_nen","response_time_ms":"thoi_gian_dap_ung","brightness_nit":"do_sang","static_contrast_ratio":"do_tuong_phan_tinh","touchscreen":"man_hinh_cam_ung","speaker":"loa","vesa":"vesa","power_consumption_watt":"dien_nang_tieu_thu"},
    "printers": {"print_speed_ppm":"toc_do_in","print_resolution_dpi":"chat_luong_in_do_net","monthly_duty_cycle":"cong_suat_theo_nghiep_vu","paper_capacity":"khay_nap_giay","supports_duplex":"loai_giay_in_2_mat","connection_types":"ket_noi","printer_type":"loai_san_pham","ink_type":"loai_muc_in","power_watt":"cong_suat_dau_ra"},
    "tablets": {"screen_size_inch":"kich_thuoc_man_hinh","battery_capacity_mah":"dung_luong_pin","ram_gb":"ram","storage_gb":"dung_luong_luu_tru","available_storage_gb":"dung_luong_kha_dung","cpu_model":"chip_xu_ly_cpu","cpu_speed_ghz":"toc_do_cpu","gpu_model":"chip_do_hoa_gpu","operating_system":"he_dieu_hanh","supports_sim":"sim","supports_calling":"thuc_hien_cuoc_goi","water_resistance":"chuan_chong_nuoc_bui","max_charging_watt":"ho_tro_sac_toi_da","weight_g":"khoi_luong_may"},
}


def _parser_for(key: str) -> Parser:
    if key in {"inverter","has_external_water_dispenser","has_auto_ice","dryer_supported","has_booster_pump","gps","supports_sim","supports_calling","wifi","touchscreen","speaker","vesa","supports_duplex"}:
        return common.parse_boolean
    if key == "capacity_btu":
        return common.parse_capacity_btu
    if key == "resolution_width":
        return common.parse_range_min
    if key == "resolution_height":
        return common.parse_range_max
    if key == "program_count":
        return common.parse_list_count
    if key.endswith("_months"):
        return common.parse_duration_months
    if key.endswith("_hours"):
        return common.parse_duration_hours
    if key.endswith("_minutes"):
        return common.parse_duration_minutes
    if key.endswith(("_min", "_min_m2", "_min_mhz")):
        return common.parse_range_min
    if key.endswith(("_max", "_max_m2", "_max_mhz")):
        return common.parse_range_max
    if key.endswith("_liter"):
        return common.parse_capacity_liter
    if key.endswith(("_mm",)):
        return common.parse_dimension
    if key.endswith("_kg"):
        return common.parse_weight_kg
    if key.endswith("_g"):
        return common.parse_weight_g
    if key.endswith("_watt"):
        return common.parse_power_watt
    if "kwh" in key:
        return common.parse_energy_kwh
    if key.endswith("_inch"):
        return common.parse_screen_size_inch
    if key.endswith("_gb"):
        return common.parse_storage_gb
    if key.endswith(("_types", "_features", "_os")):
        return common.parse_list
    if any(token in key for token in ("model","type","technology","rating","standard","mode","band","system","resistance")):
        return common.normalize_text
    return common.parse_decimal


def _data_type(key: str) -> str:
    if _parser_for(key) is common.parse_boolean:
        return "boolean"
    if _parser_for(key) is common.parse_list:
        return "array"
    if _parser_for(key) is common.normalize_text:
        return "text"
    return "number"


def _unit(key: str) -> str | None:
    suffixes = {"_liter":"l","_mm":"mm","_kg":"kg","_g":"g","_watt":"W","_kw":"kW","_kwh":"kWh","_inch":"inch","_gb":"GB","_btu":"BTU","_rpm":"rpm","_mhz":"MHz","_ghz":"GHz","_hours":"h","_minutes":"min","_meter":"m","_db":"dB","_ppm":"ppm","_dpi":"dpi","_mah":"mAh","_m2":"m²","_celsius":"°C","_percent":"%"}
    return next((unit for suffix, unit in suffixes.items() if key.endswith(suffix)), None)


def _path(key: str) -> tuple[str, ...]:
    if key in {"height_mm", "width_mm", "depth_mm"}:
        return "dimensions_mm", key.removesuffix("_mm")
    groups = {
        "cpu_":"cpu","gpu_":"gpu","ram_":"memory","max_ram_":"memory",
        "storage_":"storage","available_storage_":"storage","screen_":"display",
        "resolution_":"display","panel_":"display","brightness_":"display",
        "battery_":"battery","charging_":"battery","recommended_users_":"recommended_users",
    }
    for prefix, group in groups.items():
        if key.startswith(prefix):
            return group, key.removeprefix(prefix)
    if "capacity_liter" in key:
        if key == "capacity_liter":
            return "capacity", "total_liter"
        return "capacity", key.removesuffix("_capacity_liter") + "_liter"
    if key.startswith(("energy_", "power_")) or key == "inverter":
        return "energy", key
    return "attributes", key


def _build_registry() -> dict[str, CategoryConfig]:
    result: dict[str, CategoryConfig] = {}
    for code, (name, slug, files) in CATEGORY_META.items():
        attributes = tuple(
            AttributeConfig(
                key=key,
                source_column=source,
                display_name=key.replace("_", " ").capitalize(),
                data_type=_data_type(key),
                unit=_unit(key),
                group_name=_path(key)[0],
                parser=_parser_for(key),
                normalized_path=_path(key),
            )
            for key, source in SOURCE_COLUMNS[code].items()
        )
        result[code] = CategoryConfig(code, name, slug, files, attributes)
    return result


CATEGORY_REGISTRY = _build_registry()
FILE_TO_CATEGORY = {
    file_name.casefold(): config
    for config in CATEGORY_REGISTRY.values()
    for file_name in config.file_names
}


def category_for_file(file_name: str) -> CategoryConfig | None:
    return FILE_TO_CATEGORY.get(file_name.casefold())
