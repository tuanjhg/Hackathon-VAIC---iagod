"""S3 dialogue-policy tests (STT17+18, ADR C3).

Covers the 3 ambiguity levels (Cao / Vừa / Thấp), the never-re-ask invariant,
the max-3-slots-per-batch cap, and the "increment fails -> downgrade to
proceed" path. Uses the real ``may_lanh`` slot profile on disk (2 required +
4 optional slots), so ``load_slot_profile`` needs no mocking.
"""

import pytest

from src.pipeline.need_profile import MAX_CLARIFY_ROUNDS, NeedProfile
from src.pipeline.s3_policy import PolicyDecision, decide_policy

CATEGORY = "may_lanh"
REQUIRED = ("ngan_sach_max", "dien_tich_m2")


def _filled_required() -> dict[str, object]:
    return {"ngan_sach_max": 15_000_000, "dien_tich_m2": 20}


# --- Level: Cao (High) --------------------------------------------------------


def test_cao_when_required_slot_missing() -> None:
    profile = NeedProfile(category=CATEGORY)  # both required slots unfilled
    decision = decide_policy(profile, candidate_count=50)

    assert isinstance(decision, PolicyDecision)
    assert decision.level == "cao"
    assert decision.action == "ask"
    # required slots must come first in the batch
    names = [s.name for s in decision.slots_to_ask]
    assert names[0] in REQUIRED
    assert set(REQUIRED) <= set(names)
    assert decision.question_reason is not None
    assert decision.proceeded_with_assumptions == []
    # a clarify round was consumed
    assert profile.clarify_rounds == 1


def test_cao_when_candidate_count_high_even_though_required_filled() -> None:
    profile = NeedProfile(category=CATEGORY, slots=_filled_required())
    decision = decide_policy(profile, candidate_count=40)  # > 20

    assert decision.level == "cao"
    assert decision.action == "ask"
    names = [s.name for s in decision.slots_to_ask]
    # highest-priority optionals first (rank 1,2,3), required already filled
    assert names == ["loai_phong", "nang_truc_tiep", "uu_tien"]
    assert profile.clarify_rounds == 1


# --- Level: Vừa (Medium) ------------------------------------------------------


def test_vua_asks_single_lowest_rank_optional() -> None:
    profile = NeedProfile(category=CATEGORY, slots=_filled_required())
    decision = decide_policy(profile, candidate_count=12)  # 6..20

    assert decision.level == "vua"
    assert decision.action == "ask"
    assert [s.name for s in decision.slots_to_ask] == ["loai_phong"]
    assert profile.clarify_rounds == 1


# --- Level: Thấp (Low) --------------------------------------------------------


def test_thap_low_candidate_count_proceeds_without_question() -> None:
    profile = NeedProfile(category=CATEGORY, slots=_filled_required())
    decision = decide_policy(profile, candidate_count=3)  # <= 5

    assert decision.level == "thap"
    assert decision.action == "proceed"
    assert decision.slots_to_ask == []
    assert decision.question_reason is None
    assert decision.proceeded_with_assumptions == []
    # proceeding never consumes a clarify round
    assert profile.clarify_rounds == 0


def test_rich_profile_proceeds_without_asking_for_more_optionals() -> None:
    profile = NeedProfile(
        category=CATEGORY,
        slots={**_filled_required(), "loai_phong": "phong_ngu", "uu_tien": ["em"]},
    )

    decision = decide_policy(profile, candidate_count=40)

    assert decision.level == "thap"
    assert decision.action == "proceed"
    assert profile.clarify_rounds == 0


def test_thap_quota_exhausted_adds_assumptions_for_missing_required() -> None:
    profile = NeedProfile(category=CATEGORY, clarify_rounds=MAX_CLARIFY_ROUNDS)
    decision = decide_policy(profile, candidate_count=50)  # would be Cao if quota left

    assert decision.level == "thap"
    assert decision.action == "proceed"
    assert decision.slots_to_ask == []
    # a stated default recorded for each missing required slot
    assert set(decision.proceeded_with_assumptions) == set(REQUIRED)
    assert len(profile.assumptions) == len(REQUIRED)
    # quota not exceeded
    assert profile.clarify_rounds == MAX_CLARIFY_ROUNDS


# --- Downgrade mechanism (increment_clarify_round returns False) --------------


def test_increment_failure_downgrades_to_proceed_without_assumptions() -> None:
    # quota exhausted, but all required already filled -> no assumptions needed
    profile = NeedProfile(
        category=CATEGORY, slots=_filled_required(), clarify_rounds=MAX_CLARIFY_ROUNDS
    )
    decision = decide_policy(profile, candidate_count=15)  # would be Vừa if quota left

    assert decision.action == "proceed"
    assert decision.level == "thap"
    assert decision.proceeded_with_assumptions == []
    assert decision.slots_to_ask == []
    assert profile.clarify_rounds == MAX_CLARIFY_ROUNDS


# --- Invariants ---------------------------------------------------------------


def test_never_reasks_an_already_asked_slot() -> None:
    profile = NeedProfile(category=CATEGORY, slots=_filled_required())
    profile.mark_asked("loai_phong")  # highest-priority optional, already asked

    decision = decide_policy(profile, candidate_count=40)  # Cao -> asks optionals

    names = [s.name for s in decision.slots_to_ask]
    assert "loai_phong" not in names
    # next-in-line optionals selected instead
    assert names == ["nang_truc_tiep", "uu_tien", "tra_gop"]


def test_batch_capped_at_three_slots() -> None:
    profile = NeedProfile(category=CATEGORY)  # 2 required + 4 optional = 6 askable
    decision = decide_policy(profile, candidate_count=50)

    assert decision.action == "ask"
    assert len(decision.slots_to_ask) == 3
    # required slots take precedence in the capped batch
    assert [s.name for s in decision.slots_to_ask[:2]] == list(REQUIRED)


def test_all_selected_slots_are_askable_and_get_marked() -> None:
    profile = NeedProfile(category=CATEGORY, slots=_filled_required())
    decision = decide_policy(profile, candidate_count=40)

    # after the decision, every asked slot is recorded so it is never re-asked
    for slot in decision.slots_to_ask:
        assert slot.name in profile.asked_slots
        assert profile.should_ask(slot.name) is False


def test_nothing_left_to_ask_proceeds() -> None:
    profile = NeedProfile(category=CATEGORY, slots=_filled_required())
    # mark every optional slot as already asked -> nothing askable
    profile.mark_asked("loai_phong", "nang_truc_tiep", "uu_tien", "tra_gop")

    decision = decide_policy(profile, candidate_count=18)  # medium band

    assert decision.action == "proceed"
    assert decision.level == "thap"
    assert decision.slots_to_ask == []


def test_missing_category_raises() -> None:
    profile = NeedProfile(category=None)
    with pytest.raises(ValueError, match="category"):
        decide_policy(profile, candidate_count=10)
