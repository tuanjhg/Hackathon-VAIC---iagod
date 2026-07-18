"""Slot YAML v0 tests (task 5) — 4 priority categories: máy lạnh, tủ lạnh,
tủ mát/đông, máy nước nóng. Verifies the acceptance criterion: each profile
has required/optional slots, a sample question per slot, and a catalog field
map.
"""

import pytest

from src.pipeline.slots import available_categories, load_slot_profile

PRIORITY_CATEGORIES = ["may_lanh", "tu_lanh", "tu_mat_dong", "may_nuoc_nong"]


def test_available_categories_has_all_four_priority_categories() -> None:
    assert set(PRIORITY_CATEGORIES) <= set(available_categories())


@pytest.mark.parametrize("category_key", PRIORITY_CATEGORIES)
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


def test_may_lanh_required_slots_match_workflow_doc() -> None:
    profile = load_slot_profile("may_lanh")
    required_names = {s.name for s in profile.required_slots}
    assert required_names == {"ngan_sach_max", "dien_tich_m2"}


def test_tu_lanh_required_slots_match_workflow_doc() -> None:
    profile = load_slot_profile("tu_lanh")
    required_names = {s.name for s in profile.required_slots}
    assert required_names == {"ngan_sach_max", "so_nguoi_dung"}


def test_unknown_category_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_slot_profile("does_not_exist")
