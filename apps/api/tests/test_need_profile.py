from src.pipeline.need_profile import (
    DEFAULT_PRESERVED_SLOTS,
    MAX_CLARIFY_ROUNDS,
    NeedProfile,
)

RESEARCH_EXAMPLE = {
    "category": "máy_lạnh",
    "slots": {
        "ngan_sach_max": 20000000,
        "dien_tich_m2": 18,
        "loai_phong": None,
        "nắng_trực_tiếp": None,
        "ưu_tiên": ["tiết_kiệm_điện", "êm"],
        "trả_góp": None,
    },
    "asked_slots": ["loai_phong", "nắng_trực_tiếp"],
    "clarify_rounds": 1,
    "assumptions": [],
}


def test_schema_matches_research_example() -> None:
    profile = NeedProfile(**RESEARCH_EXAMPLE)
    assert profile.model_dump() == RESEARCH_EXAMPLE


def test_defaults_are_independent_instances() -> None:
    a = NeedProfile()
    b = NeedProfile()
    a.slots["x"] = 1
    a.asked_slots.append("x")
    a.assumptions.append("y")
    assert b.slots == {}
    assert b.asked_slots == []
    assert b.assumptions == []
    assert b.category is None
    assert b.clarify_rounds == 0


# --- merge_slots -----------------------------------------------------------


def test_merge_slots_does_not_clobber_existing_value() -> None:
    profile = NeedProfile(slots={"ngan_sach_max": 20000000})
    profile.merge_slots({"ngan_sach_max": 15000000})
    assert profile.slots["ngan_sach_max"] == 20000000


def test_merge_slots_fills_null_slot() -> None:
    profile = NeedProfile(slots={"dien_tich_m2": None})
    profile.merge_slots({"dien_tich_m2": 18})
    assert profile.slots["dien_tich_m2"] == 18


def test_merge_slots_adds_new_key() -> None:
    profile = NeedProfile()
    profile.merge_slots({"loai_phong": "phòng_ngủ"})
    assert profile.slots["loai_phong"] == "phòng_ngủ"


def test_merge_slots_overwrite_flag_replaces_existing() -> None:
    profile = NeedProfile(slots={"ngan_sach_max": 20000000})
    profile.merge_slots({"ngan_sach_max": 15000000}, overwrite=True)
    assert profile.slots["ngan_sach_max"] == 15000000


def test_merge_slots_mixed_batch() -> None:
    profile = NeedProfile(slots={"ngan_sach_max": 20000000, "dien_tich_m2": None})
    profile.merge_slots({"ngan_sach_max": 9999, "dien_tich_m2": 18, "loai_phong": "khách"})
    assert profile.slots["ngan_sach_max"] == 20000000  # kept
    assert profile.slots["dien_tich_m2"] == 18  # filled
    assert profile.slots["loai_phong"] == "khách"  # added


# --- asked_slots -----------------------------------------------------------


def test_mark_asked_dedups_and_preserves_order() -> None:
    profile = NeedProfile()
    profile.mark_asked("loai_phong", "nắng_trực_tiếp")
    profile.mark_asked("loai_phong")
    profile.mark_asked("nắng_trực_tiếp", "trả_góp")
    assert profile.asked_slots == ["loai_phong", "nắng_trực_tiếp", "trả_góp"]


def test_should_ask_rules() -> None:
    profile = NeedProfile(
        slots={"ngan_sach_max": 20000000, "loai_phong": None},
        asked_slots=["nắng_trực_tiếp"],
    )
    assert profile.should_ask("ngan_sach_max") is False  # already filled
    assert profile.should_ask("nắng_trực_tiếp") is False  # already asked
    assert profile.should_ask("loai_phong") is True  # known but null, not asked
    assert profile.should_ask("trả_góp") is True  # unknown, not asked


# --- clarify_rounds hard cap ----------------------------------------------


def test_increment_clarify_round_hard_cap() -> None:
    profile = NeedProfile()
    assert MAX_CLARIFY_ROUNDS == 2
    assert profile.increment_clarify_round() is True
    assert profile.clarify_rounds == 1
    assert profile.increment_clarify_round() is True
    assert profile.clarify_rounds == 2
    # third attempt must be rejected and must not exceed the cap
    assert profile.increment_clarify_round() is False
    assert profile.clarify_rounds == 2
    # repeated over-cap attempts stay rejected and capped
    assert profile.increment_clarify_round() is False
    assert profile.clarify_rounds == 2


# --- category change -------------------------------------------------------


def test_change_category_preserves_budget_resets_others() -> None:
    profile = NeedProfile(
        category="máy_lạnh",
        slots={
            "ngan_sach_max": 20000000,
            "dien_tich_m2": 18,
            "loai_phong": "phòng_ngủ",
        },
        asked_slots=["ngan_sach_max", "dien_tich_m2", "loai_phong"],
        clarify_rounds=1,
        assumptions=["giả định phòng ngủ không nắng"],
    )
    profile.change_category("tủ_lạnh")

    assert profile.category == "tủ_lạnh"
    assert profile.slots == {"ngan_sach_max": 20000000}  # budget survives
    assert profile.asked_slots == ["ngan_sach_max"]  # reset to preserved only
    assert profile.assumptions == []  # cleared
    # clarify quota is per-conversation and must not be re-opened by a switch
    assert profile.clarify_rounds == 1


def test_change_category_default_preserved_set_is_budget() -> None:
    assert DEFAULT_PRESERVED_SLOTS == ("ngan_sach_max",)


def test_change_category_custom_preserve_list() -> None:
    profile = NeedProfile(
        category="điện_thoại",
        slots={"ngân_sách_toi_da": 5000000, "mục_đích": "chụp ảnh"},
    )
    profile.change_category("laptop", preserve_slots=["ngân_sách_toi_da"])
    assert profile.slots == {"ngân_sách_toi_da": 5000000}
    assert profile.category == "laptop"


def test_change_category_same_category_is_noop() -> None:
    profile = NeedProfile(
        category="máy_lạnh",
        slots={"ngan_sach_max": 1, "dien_tich_m2": 18},
        asked_slots=["dien_tich_m2"],
    )
    profile.change_category("máy_lạnh")
    assert profile.slots == {"ngan_sach_max": 1, "dien_tich_m2": 18}
    assert profile.asked_slots == ["dien_tich_m2"]


# --- assumptions -----------------------------------------------------------


def test_add_assumption_appends() -> None:
    profile = NeedProfile()
    profile.add_assumption("Em tạm tính cho phòng ngủ không nắng trực tiếp")
    profile.add_assumption("Giả định không cần trả góp")
    assert profile.assumptions == [
        "Em tạm tính cho phòng ngủ không nắng trực tiếp",
        "Giả định không cần trả góp",
    ]
