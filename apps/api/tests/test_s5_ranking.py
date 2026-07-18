"""Tests for S5 fit-score ranking (ADR C4/C5).

Pure-function stage: no DB, no LLM, no I/O beyond reading the real hand-authored
``may_lanh`` slot profile from disk (so field names/`catalog_field` mappings stay
in lock-step with the actual dataset rather than being re-mocked here).

Candidate dicts mirror the S4 → S5 contract: ``sku``, ``name``, ``specs`` (a
``Product.specs_json``-shaped dict of arbitrary per-category keys), ``price``
(int VND or None), ``in_stock`` (None in this dataset — no stock signal exists).
"""

from typing import Any

from src.pipeline.need_profile import NeedProfile
from src.pipeline.s5_ranking import (
    PRIORITY_SLOT_NAME,
    RankingResult,
    ScoreBreakdown,
    TradeOff,
    rank_candidates,
)
from src.pipeline.slots import SlotProfile, load_slot_profile

SLOT_PROFILE: SlotProfile = load_slot_profile("may_lanh")
BUDGET_SLOT = "ngan_sach_max"


def _profile(**slots: Any) -> NeedProfile:
    return NeedProfile(category="may_lanh", slots=dict(slots))


def _cand(
    sku: str,
    *,
    price: int | None = 15_000_000,
    in_stock: bool | None = None,
    **specs: Any,
) -> dict[str, Any]:
    return {
        "sku": sku,
        "name": f"Máy lạnh {sku}",
        "specs": dict(specs),
        "price": price,
        "in_stock": in_stock,
    }


# A 5-candidate máy lạnh set covering the priority criteria (inverter,
# energy_efficiency, noise_db_indoor). "E" is deliberately missing
# noise_db_indoor — a real dirty-data case for the honesty guardrail.
FLEET = [
    _cand("A", price=15_000_000, inverter=True, energy_efficiency=6.5, noise_db_indoor=35),
    _cand("B", price=14_000_000, inverter=False, energy_efficiency=4.0, noise_db_indoor=24),
    _cand("C", price=16_000_000, inverter=True, energy_efficiency=5.5, noise_db_indoor=29),
    _cand("D", price=13_000_000, inverter=False, energy_efficiency=4.5, noise_db_indoor=31),
    _cand("E", price=12_000_000, inverter=True, energy_efficiency=5.0),  # no noise data
]


def _by_sku(result: RankingResult) -> dict[str, ScoreBreakdown]:
    seen = {b.sku: b for b in result.top}
    if result.anti_pick is not None:
        seen.setdefault(result.anti_pick.sku, result.anti_pick)
    return seen


def _find_trade_off(result: RankingResult, sku_x: str, sku_y: str) -> TradeOff | None:
    pair = {sku_x, sku_y}
    for t in result.trade_offs:
        if {t.sku_a, t.sku_b} == pair:
            return t
    return None


# --------------------------------------------------------------------------- #
# Degenerate inputs                                                           #
# --------------------------------------------------------------------------- #
def test_empty_candidate_list_returns_empty_result_no_crash() -> None:
    result = rank_candidates([], _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    assert isinstance(result, RankingResult)
    assert result.top == []
    assert result.anti_pick is None
    assert result.anti_pick_reason is None
    assert result.trade_offs == []


def test_single_candidate_top_has_one_and_no_anti_pick() -> None:
    result = rank_candidates([FLEET[0]], _profile(uu_tien=["em"]), SLOT_PROFILE)
    assert len(result.top) == 1
    assert result.top[0].sku == "A"
    assert result.anti_pick is None
    assert result.anti_pick_reason is None
    assert result.trade_offs == []


# --------------------------------------------------------------------------- #
# Weighting from stated priority actually changes the ranking                 #
# --------------------------------------------------------------------------- #
def test_stated_priority_weighting_changes_top_pick() -> None:
    energy = rank_candidates(FLEET, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    quiet = rank_candidates(FLEET, _profile(uu_tien=["em"]), SLOT_PROFILE)

    # Same candidates, different stated priority -> different #1 pick.
    assert energy.top[0].sku != quiet.top[0].sku
    assert energy.top[0].sku == "A"  # best energy_efficiency + inverter
    assert quiet.top[0].sku == "C"  # best weighted fit once low-noise dominates


def test_priority_slot_name_is_the_real_ascii_field() -> None:
    # Guard against silently renaming the priority slot; it IS "uu_tien" in data.
    assert PRIORITY_SLOT_NAME == "uu_tien"
    assert any(s.name == PRIORITY_SLOT_NAME for s in SLOT_PROFILE.optional_slots)


# --------------------------------------------------------------------------- #
# Missing field: penalized AND surfaced, never silently dropped               #
# --------------------------------------------------------------------------- #
def test_missing_stated_field_is_flagged_and_penalized_not_dropped() -> None:
    cands = [
        _cand("X", inverter=True, energy_efficiency=6.0, noise_db_indoor=25),
        _cand("Y", inverter=True, energy_efficiency=6.0),  # missing noise (stated)
        _cand("Z", inverter=False, energy_efficiency=3.0, noise_db_indoor=40),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["em"]), SLOT_PROFILE)

    y = _by_sku(result)["Y"]
    # Surfaced, not hidden.
    assert "noise_db_indoor" in y.missing_fields
    # Penalized: a namespaced negative penalty entry exists in the breakdown.
    penalties = [v for k, v in y.per_criterion.items() if k.startswith("penalty:missing")]
    assert penalties and all(v < 0 for v in penalties)
    # Still present in the result — dirty data does not kill the product.
    assert "Y" in {b.sku for b in result.top}


def test_breakdown_sums_to_total_score() -> None:
    result = rank_candidates(FLEET, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    for b in _by_sku(result).values():
        assert abs(sum(b.per_criterion.values()) - b.total_score) < 1e-9


# --------------------------------------------------------------------------- #
# Trade-off extraction cites STATED-priority criteria only                    #
# --------------------------------------------------------------------------- #
def test_trade_off_only_cites_stated_priority_criteria() -> None:
    # tiet_kiem_dien -> stated = {inverter, energy_efficiency}; noise is UNSTATED.
    # P and Q reverse on the two stated criteria AND differ on noise (unstated).
    cands = [
        _cand("P", inverter=True, energy_efficiency=4.0, noise_db_indoor=25),
        _cand("Q", inverter=False, energy_efficiency=6.0, noise_db_indoor=35),
        _cand("R", inverter=True, energy_efficiency=5.0, noise_db_indoor=30),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)

    trade = _find_trade_off(result, "P", "Q")
    assert trade is not None
    cited = set(trade.a_wins_on) | set(trade.b_wins_on) | set(trade.values)
    # The unstated criterion must NOT leak into the trade-off, even though the
    # pair genuinely differs on it.
    assert "noise_db_indoor" not in cited
    # A stated criterion must be present (it is a real trade-off).
    assert cited & {"inverter", "energy_efficiency"}
    # Direction actually reverses -> both sides win at least one criterion.
    assert trade.a_wins_on and trade.b_wins_on


def test_no_trade_off_when_one_candidate_dominates_stated_criteria() -> None:
    # W beats V on every stated criterion -> no reversal -> no trade-off emitted.
    cands = [
        _cand("V", inverter=False, energy_efficiency=4.0, noise_db_indoor=24),
        _cand("W", inverter=True, energy_efficiency=6.0, noise_db_indoor=40),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    assert _find_trade_off(result, "V", "W") is None


# --------------------------------------------------------------------------- #
# Anti-pick heuristic is deterministic and drawn from the priced pool         #
# --------------------------------------------------------------------------- #
def test_anti_pick_is_lowest_scoring_priced_candidate() -> None:
    cands = [
        _cand("GOOD", price=15_000_000, inverter=True, energy_efficiency=6.5, noise_db_indoor=25),
        _cand("LP", price=10_000_000, inverter=False, energy_efficiency=3.0, noise_db_indoor=42),
        # Worst specs overall, but UNPRICED -> must NOT be the anti-pick.
        _cand("UP", price=None, inverter=False, energy_efficiency=2.0, noise_db_indoor=48),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)

    assert result.anti_pick is not None
    assert result.anti_pick.sku == "LP"
    assert result.anti_pick.price is not None
    assert isinstance(result.anti_pick_reason, str) and result.anti_pick_reason


def test_anti_pick_falls_back_to_overall_lowest_when_no_prices() -> None:
    cands = [
        _cand("N1", price=None, inverter=True, energy_efficiency=6.0, noise_db_indoor=25),
        _cand("N2", price=None, inverter=False, energy_efficiency=3.0, noise_db_indoor=45),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    assert result.anti_pick is not None
    assert result.anti_pick.sku == "N2"


# --------------------------------------------------------------------------- #
# Over-budget: deprioritized, never hard-excluded                            #
# --------------------------------------------------------------------------- #
def test_over_budget_candidate_scores_lower_but_still_appears() -> None:
    cands = [
        _cand("IN", price=15_000_000, inverter=True, energy_efficiency=6.0, noise_db_indoor=28),
        _cand("OVER", price=25_000_000, inverter=True, energy_efficiency=6.0, noise_db_indoor=28),
    ]
    profile = _profile(uu_tien=["tiet_kiem_dien"], ngan_sach_max=20_000_000)
    result = rank_candidates(cands, profile, SLOT_PROFILE)

    breakdowns = _by_sku(result)
    assert "OVER" in breakdowns  # not hard-excluded
    assert breakdowns["IN"].total_score > breakdowns["OVER"].total_score
    over_penalty = [v for k, v in breakdowns["OVER"].per_criterion.items() if "over_budget" in k]
    assert over_penalty and over_penalty[0] < 0
    # Identical-spec in-budget twin carries no such penalty.
    assert not any("over_budget" in k for k in breakdowns["IN"].per_criterion)


# --------------------------------------------------------------------------- #
# price=None stays None and remains scorable/rankable                        #
# --------------------------------------------------------------------------- #
def test_unpriced_candidate_is_still_rankable_and_price_stays_none() -> None:
    cands = [
        _cand("PR", price=15_000_000, inverter=False, energy_efficiency=3.5, noise_db_indoor=40),
        _cand("NP", price=None, inverter=True, energy_efficiency=6.5, noise_db_indoor=24),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    # Strong-but-unpriced candidate can still win the ranking.
    assert result.top[0].sku == "NP"
    assert result.top[0].price is None


def test_in_stock_bonus_breaks_tie_between_identical_specs() -> None:
    cands = [
        _cand("STOCKED", in_stock=True, inverter=True, energy_efficiency=6.0, noise_db_indoor=28),
        _cand("UNKNOWN", in_stock=None, inverter=True, energy_efficiency=6.0, noise_db_indoor=28),
    ]
    result = rank_candidates(cands, _profile(uu_tien=["tiet_kiem_dien"]), SLOT_PROFILE)
    assert result.top[0].sku == "STOCKED"


# --------------------------------------------------------------------------- #
# Right-sizing (soft oversize penalty — deprioritize, never exclude)          #
# --------------------------------------------------------------------------- #
def test_oversized_aircon_ranks_below_right_sized_for_small_room() -> None:
    # 18m² → btu_can 10800, 1.3× tolerance = 14040. A 12000 BTU unit is
    # right-sized; an 18000 BTU one is oversized. Otherwise identical specs, so
    # the oversize penalty must decide the order (right-sized on top).
    profile = _profile(dien_tich_m2=18, uu_tien=["tiet_kiem_dien"])
    cands = [
        _cand("BIG", price=13_000_000, inverter=True, energy_efficiency=6.0, capacity_btu=18000),
        _cand("RIGHT", price=13_000_000, inverter=True, energy_efficiency=6.0, capacity_btu=12000),
    ]
    result = rank_candidates(cands, profile, SLOT_PROFILE)

    assert result.top[0].sku == "RIGHT"
    big = _by_sku(result)["BIG"]
    assert any(k.startswith("penalty:oversize") for k in big.per_criterion)


def test_no_oversize_penalty_when_room_area_unknown() -> None:
    # Without dien_tich_m2 there is no need to size against → never penalized.
    profile = _profile(uu_tien=["tiet_kiem_dien"])
    cands = [_cand("BIG", inverter=True, energy_efficiency=6.0, capacity_btu=18000)]
    result = rank_candidates(cands, profile, SLOT_PROFILE)

    big = _by_sku(result)["BIG"]
    assert not any(k.startswith("penalty:oversize") for k in big.per_criterion)


def test_adequate_capacity_within_tolerance_is_not_penalized() -> None:
    # 25m² → btu_can 15000, 1.3× = 19500; an 18000 BTU unit is within tolerance.
    profile = _profile(dien_tich_m2=25, uu_tien=["tiet_kiem_dien"])
    cands = [_cand("OK", inverter=True, energy_efficiency=6.0, capacity_btu=18000)]
    result = rank_candidates(cands, profile, SLOT_PROFILE)

    ok = _by_sku(result)["OK"]
    assert not any(k.startswith("penalty:oversize") for k in ok.per_criterion)
