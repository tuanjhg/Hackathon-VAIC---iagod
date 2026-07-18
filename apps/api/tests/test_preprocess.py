"""S1 preprocessing tests (task 8) — 10 "dirty" Vietnamese sentences covering
money shorthand (tr/củ/bare-m/VN number words/ranges), unit conversion
(m², HP→BTU, lít, W) and category-dict detection, per
`docs/research/dmx-ai-workflow-v1.md` §3.
"""

from src.pipeline.preprocess import (
    detect_category,
    hp_to_btu,
    parse_money,
    parse_units,
    run_s1,
)


def test_money_and_category_from_slang_amount() -> None:
    r = run_s1("tui muốn mua máy lạnh khoảng 20 củ")
    assert r.category_hint == "may_lanh"
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(20_000_000, 20_000_000)]


def test_area_m2_not_confused_with_money() -> None:
    r = run_s1("phòng 18m2 thì nên lắp máy lạnh mấy HP")
    assert r.category_hint == "may_lanh"
    assert r.money == []
    assert [(u.kind, u.value) for u in r.units] == [("area_m2", 18.0)]


def test_hp_to_btu_and_money_range() -> None:
    r = run_s1("máy lạnh 1.5 ngựa giá tầm 15-20tr")
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(15_000_000, 20_000_000)]
    assert [(u.kind, u.value) for u in r.units] == [("power_btu", 12_000.0)]


def test_liter_volume_and_money_shorthand() -> None:
    r = run_s1("tủ lạnh dung tích 300 lít giá khoảng 10tr")
    assert r.category_hint == "tu_lanh"
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(10_000_000, 10_000_000)]
    assert [(u.kind, u.value) for u in r.units] == [("volume_liter", 300.0)]


def test_bare_m_money_slang_and_short_category_code() -> None:
    r = run_s1("ngân sách tầm 20m cho cái tl")
    assert r.category_hint == "tu_lanh"
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(20_000_000, 20_000_000)]
    assert r.units == []


def test_watt_extraction_for_water_heater() -> None:
    r = run_s1("cho hỏi máy nước nóng công suất 4500W giá nhiêu")
    assert r.category_hint == "may_nuoc_nong"
    assert [(u.kind, u.value) for u in r.units] == [("power_watt", 4500.0)]


def test_tu_mat_dong_liters_and_full_word_money() -> None:
    r = run_s1("mình cần cái tủ mát khoảng 300 lít, tầm 10 triệu")
    assert r.category_hint == "tu_mat_dong"
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(10_000_000, 10_000_000)]
    assert [(u.kind, u.value) for u in r.units] == [("volume_liter", 300.0)]


def test_vietnamese_number_words_and_teencode_expansion() -> None:
    r = run_s1("máy lạnh 1 hp giá hai chục triệu được ko")
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(20_000_000, 20_000_000)]
    assert [(u.kind, u.value) for u in r.units] == [("power_btu", 9_000.0)]
    # "ko" (teencode) expands to "không" in the normalized text S2 also sees.
    assert "không" in r.normalized


def test_second_area_phrasing_variant() -> None:
    r = run_s1("phòng ngủ 12m2 lắp máy lạnh loại nào")
    assert r.category_hint == "may_lanh"
    assert r.money == []
    assert [(u.kind, u.value) for u in r.units] == [("area_m2", 12.0)]


def test_money_range_and_code_switch_preserved() -> None:
    r = run_s1("ngân sách 15tr-20tr cho máy giặt inverter")
    assert r.category_hint == "may_giat"
    assert [(m.min_vnd, m.max_vnd) for m in r.money] == [(15_000_000, 20_000_000)]
    # Code-switched English token is never translated/stripped.
    assert "inverter" in r.normalized


def test_hp_to_btu_table_values() -> None:
    assert hp_to_btu(1.0) == 9_000
    assert hp_to_btu(1.5) == 12_000
    assert hp_to_btu(2.0) == 18_000


def test_parse_money_ignores_plain_area_number() -> None:
    assert parse_money("phòng 20m2") == []


def test_detect_category_returns_none_when_absent() -> None:
    assert detect_category("hôm nay trời đẹp quá") is None


def test_parse_units_multiple_in_one_sentence() -> None:
    units = parse_units("máy lạnh 2 hp cho phòng 25m2")
    kinds = {u.kind for u in units}
    assert kinds == {"power_btu", "area_m2"}
