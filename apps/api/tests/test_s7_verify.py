"""Tests for S7 per-claim verifier (STT31-35, ADR C6, guardrail Tầng 2/3).

Pure-function stage: no DB, no LLM, no I/O. Every fixture is hand-built inline —
a small ``prose`` string with bracket markers (the S6 → S7 contract), a
``marker_map`` and a flat per-SKU ``facts`` dict. The verifier extracts atomic
number+unit claims, binds each to the nearest preceding marker, and checks it
against the corresponding fact field (recomputing DERIVED differences rather
than string-matching them).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from src.verifier import (
    ClaimVerdict,
    VerificationResult,
    verify,
)

# --------------------------------------------------------------------------- #
# Shared fixtures — a 4-SKU máy lạnh turn.                                     #
# ``sku_c`` has *only* a price (no noise/warranty) — a real dirty-data case.   #
# --------------------------------------------------------------------------- #
MARKER_MAP: dict[str, str] = {
    "[1]": "sku_a",
    "[2]": "sku_b",
    "[3]": "sku_c",
    "[A]": "sku_x",
}

FACTS: dict[str, dict[str, Any]] = {
    "sku_a": {
        "noise_db_indoor": 29,
        "capacity_btu": 24000,
        "price": 15_990_000,
        "energy_efficiency": 6.23,
        "warranty_years_compressor": 10,
    },
    "sku_b": {"noise_db_indoor": 31, "price": 17_990_000},
    "sku_c": {"price": 13_990_000},  # no noise / no warranty
    "sku_x": {"noise_db_indoor": 35},
}


def _only(result: VerificationResult) -> ClaimVerdict:
    assert len(result.claims) == 1, result.claims
    return result.claims[0]


# --------------------------------------------------------------------------- #
# Direct claims: match / mismatch / unverifiable                              #
# --------------------------------------------------------------------------- #
def test_correct_direct_claim_matches() -> None:
    res = verify("[1] có độ ồn 29dB.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.verdict == "match"
    assert claim.kind == "direct"
    assert claim.sku == "sku_a"
    assert claim.marker == "[1]"
    assert claim.field == "noise_db_indoor"
    assert claim.actual_value == 29
    assert res.per_claim_error_rate == 0.0


def test_wrong_direct_claim_mismatches() -> None:
    res = verify("[1] có độ ồn 25dB.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.verdict == "mismatch"
    assert claim.field == "noise_db_indoor"
    assert claim.actual_value == 29
    assert res.per_claim_error_rate == 1.0


def test_claim_about_absent_field_is_unverifiable() -> None:
    # sku_c has no noise field at all → nothing to check against.
    res = verify("[3] có độ ồn 28dB.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.verdict == "unverifiable"
    assert claim.sku == "sku_c"
    assert claim.actual_value is None


def test_price_claim_matches_against_price_field() -> None:
    res = verify("[1] giá 15.990.000đ.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.verdict == "match"
    assert claim.field == "price"
    assert claim.claimed_value == 15_990_000


def test_shorthand_price_forms_parse_and_match() -> None:
    # "17tr99" == 17_990_000 and "13 triệu" component checks the money grammar.
    res = verify("[2] giá 17tr99.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.claimed_value == 17_990_000
    assert claim.verdict == "match"


# --------------------------------------------------------------------------- #
# Derived numbers (STT32): recompute, do NOT literal-match                     #
# --------------------------------------------------------------------------- #
def test_correct_derived_difference_is_not_flagged_mismatch() -> None:
    # 17_990_000 - 15_990_000 == 2_000_000 == "2 triệu". The literal number
    # 2_000_000 appears in NO fact — it MUST be recomputed, not string-matched.
    res = verify("[1] rẻ hơn [2] 2 triệu.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.kind == "derived"
    assert claim.verdict == "match"
    assert claim.verdict != "mismatch"
    assert claim.actual_value == 2_000_000


def test_incorrect_derived_difference_mismatches() -> None:
    # Real difference is 2 triệu; prose claims 3 triệu → MISMATCH.
    res = verify("[1] rẻ hơn [2] 3 triệu.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.kind == "derived"
    assert claim.verdict == "mismatch"
    assert claim.actual_value == 2_000_000


def test_parenthesised_values_stay_direct_not_derived() -> None:
    # The canonical S6 prose: comparative sentence, but the numbers are
    # parenthesised per-SKU direct annotations, NOT a computed difference.
    prose = "[1] êm hơn (29dB) so với [2] (31dB). [3] phù hợp ngân sách."
    res = verify(prose, MARKER_MAP, FACTS)
    assert [c.kind for c in res.claims] == ["direct", "direct"]
    assert [c.verdict for c in res.claims] == ["match", "match"]
    assert res.per_claim_error_rate == 0.0


# --------------------------------------------------------------------------- #
# Metric (STT: per-claim error rate)                                          #
# --------------------------------------------------------------------------- #
def test_per_claim_error_rate_on_mixed_set() -> None:
    prose = "[1] có độ ồn 29dB, công suất 24000 BTU, giá 15.990.000đ. [2] có độ ồn 20dB."
    res = verify(prose, MARKER_MAP, FACTS)
    assert len(res.claims) == 4
    verdicts = [c.verdict for c in res.claims]
    assert verdicts.count("mismatch") == 1  # only the [2] 20dB claim
    assert res.per_claim_error_rate == 0.25


# --------------------------------------------------------------------------- #
# Honesty check (STT34)                                                       #
# --------------------------------------------------------------------------- #
def test_honesty_violation_when_concrete_value_for_absent_field() -> None:
    # sku_c has no warranty field, yet prose states a concrete "10 năm".
    res = verify("[3] bảo hành 10 năm.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.verdict == "unverifiable"
    assert len(res.honesty_violations) == 1
    assert "sku_c" in res.honesty_violations[0]


def test_no_honesty_violation_when_honesty_phrase_present() -> None:
    # Same absent-field situation, but the sentence owns up with a honesty phrase.
    res = verify(
        "[3] bảo hành 10 năm nhưng chưa có dữ liệu chính thức.", MARKER_MAP, FACTS
    )
    claim = _only(res)
    assert claim.verdict == "unverifiable"
    assert res.honesty_violations == []


# --------------------------------------------------------------------------- #
# Freshness check (STT35)                                                     #
# --------------------------------------------------------------------------- #
def test_freshness_flag_when_snapshot_is_stale() -> None:
    stale = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    res = verify("[1] giá 15.990.000đ.", MARKER_MAP, FACTS, fetched_at={"sku_a": stale})
    assert len(res.freshness_flags) == 1
    assert "sku_a" in res.freshness_flags[0]


def test_no_freshness_flag_when_snapshot_is_fresh() -> None:
    fresh = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    res = verify("[1] giá 15.990.000đ.", MARKER_MAP, FACTS, fetched_at={"sku_a": fresh})
    assert res.freshness_flags == []


def test_no_freshness_flag_when_not_provided() -> None:
    res = verify("[1] giá 15.990.000đ.", MARKER_MAP, FACTS)
    assert res.freshness_flags == []


def test_freshness_threshold_is_configurable() -> None:
    ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    # 2h old is fresh under the default 24h but stale under a 1h threshold.
    fresh = verify("[1] giá 15.990.000đ.", MARKER_MAP, FACTS, fetched_at={"sku_a": ts})
    stale = verify(
        "[1] giá 15.990.000đ.",
        MARKER_MAP,
        FACTS,
        fetched_at={"sku_a": ts},
        freshness_threshold_hours=1.0,
    )
    assert fresh.freshness_flags == []
    assert len(stale.freshness_flags) == 1


# --------------------------------------------------------------------------- #
# Robustness: empty / no markers / dangling claims                            #
# --------------------------------------------------------------------------- #
def test_empty_prose_gives_no_claims() -> None:
    res = verify("", MARKER_MAP, FACTS)
    assert res.claims == []
    assert res.per_claim_error_rate == 0.0
    assert res.honesty_violations == []
    assert res.freshness_flags == []


def test_prose_without_markers_or_numbers_gives_no_claims() -> None:
    res = verify("Xin chào, đây là vài gợi ý cho anh.", MARKER_MAP, FACTS)
    assert res.claims == []


def test_claim_before_any_marker_is_unverifiable_not_crash() -> None:
    res = verify("Giá tầm 20 triệu nhé. [1] có độ ồn 29dB.", MARKER_MAP, FACTS)
    # "20 triệu" precedes every marker → no SKU binding → unverifiable, skipped.
    dangling = res.claims[0]
    assert dangling.sku is None
    assert dangling.marker is None
    assert dangling.verdict == "unverifiable"
    # The bound claim still verifies normally.
    assert res.claims[1].sku == "sku_a"
    assert res.claims[1].verdict == "match"
    # A dangling unverifiable claim is never counted as a mismatch.
    assert res.per_claim_error_rate == 0.0


def test_unknown_marker_resolves_to_unverifiable() -> None:
    res = verify("[9] có độ ồn 29dB.", MARKER_MAP, FACTS)
    claim = _only(res)
    assert claim.verdict == "unverifiable"
    assert claim.sku is None
