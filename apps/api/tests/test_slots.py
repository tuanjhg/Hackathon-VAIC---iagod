"""Slot-profile coverage and structure tests for all catalog categories."""

import pytest

from src.pipeline.preprocess import CATEGORY_DICT
from src.pipeline.slots import available_categories, load_slot_profile

PRIORITY_CATEGORIES = ["may_lanh", "tu_lanh", "tu_mat_dong", "may_nuoc_nong"]
ALL_CATEGORIES = sorted(CATEGORY_DICT)


def test_available_categories_matches_all_fourteen_catalog_categories() -> None:
    assert available_categories() == ALL_CATEGORIES


@pytest.mark.parametrize("category_key", ALL_CATEGORIES)
def test_slot_profile_structure(category_key: str) -> None:
    profile = load_slot_profile(category_key)

    assert profile.category_key == category_key
    assert profile.category_label

    assert len(profile.required_slots) >= 2
    assert len(profile.optional_slots) >= 3
    assert profile.catalog_field_map

    for slot in profile.required_slots + profile.optional_slots:
        assert slot.sample_question.strip().endswith("?")
        assert slot.name

    # Optional slots are ranked so S3 can pick the highest information-gain
    # ones first when time/quota is limited.
    ranks = [s.priority_rank for s in profile.optional_slots if s.priority_rank is not None]
    assert ranks == sorted(ranks)


@pytest.mark.parametrize("category_key", ALL_CATEGORIES)
def test_every_category_has_budget_and_an_industry_need(category_key: str) -> None:
    profile = load_slot_profile(category_key)
    required_names = [slot.name for slot in profile.required_slots]
    assert required_names[0] == "ngan_sach_max"
    assert len(required_names) >= 2


def test_may_lanh_required_slots_match_workflow_doc() -> None:
    profile = load_slot_profile("may_lanh")
    required_names = {s.name for s in profile.required_slots}
    assert required_names == {"ngan_sach_max", "dien_tich_m2"}


def test_tu_lanh_required_slots_match_workflow_doc() -> None:
    profile = load_slot_profile("tu_lanh")
    required_names = {s.name for s in profile.required_slots}
    assert required_names == {"ngan_sach_max", "so_nguoi_dung"}


def test_tu_lanh_declares_ranking_criteria() -> None:
    profile = load_slot_profile("tu_lanh")
    by_field = {c.field: c for c in profile.ranking_criteria}
    assert by_field["inverter"].direction == "boolean_pref"
    cap = by_field["capacity_total_l"]
    assert cap.direction == "target"
    assert cap.target == "dung_tich_can"


def test_may_lanh_has_no_ranking_criteria() -> None:
    # uu_tien categories keep the legacy path; the field defaults to empty.
    assert load_slot_profile("may_lanh").ranking_criteria == []


RAW_CATEGORIES_WITH_CRITERIA = [
    "pc_de_ban", "may_tinh_bang", "man_hinh", "may_in", "may_say",
    "may_nuoc_nong", "tu_mat_dong", "micro_thu_am", "micro_karaoke",
]


@pytest.mark.parametrize("category_key", RAW_CATEGORIES_WITH_CRITERIA)
def test_raw_category_declares_specs_ranking_criteria(category_key: str) -> None:
    profile = load_slot_profile(category_key)
    assert profile.ranking_criteria, f"{category_key} has no ranking_criteria"
    for criterion in profile.ranking_criteria:
        assert criterion.direction in {"higher_better", "lower_better", "boolean_pref"}
        # criteria reference parsed specs keys, never the raw label paths
        assert " " not in criterion.field and "." not in criterion.field


def test_unknown_category_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_slot_profile("does_not_exist")
