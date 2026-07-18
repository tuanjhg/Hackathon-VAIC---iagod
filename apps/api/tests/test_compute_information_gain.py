"""Tests for the offline information-gain precompute (STT19).

The script under test lives at repo-root ``scripts/compute_information_gain.py``
(it is an ingest-time tool, not part of the importable ``src`` package), so we
put it on ``sys.path`` with the same trick the script itself uses to reach
``apps/api``. The core assertion is the entropy property: a high-variety value
distribution scores higher Shannon entropy than a near-constant one.
"""

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import compute_information_gain as cig  # noqa: E402

_MAY_LANH_DATA = _REPO_ROOT / "data" / "realdata" / "processed" / "may_lanh.json"


# --- shannon_entropy ----------------------------------------------------------


def test_uniform_four_buckets_is_two_bits() -> None:
    assert cig.shannon_entropy([25, 25, 25, 25]) == pytest.approx(2.0)


def test_single_bucket_is_zero_entropy() -> None:
    assert cig.shannon_entropy([100]) == 0.0
    assert cig.shannon_entropy([]) == 0.0


def test_high_variety_scores_higher_than_near_constant() -> None:
    near_constant = cig.bucket_field_values(["a"] * 99 + ["b"])
    high_variety = cig.bucket_field_values([f"v{i % 5}" for i in range(100)])

    low = cig.shannon_entropy(list(near_constant.values()))
    high = cig.shannon_entropy(list(high_variety.values()))

    assert high > low
    # 5 equal categories -> log2(5) ~= 2.32 bits
    assert high == pytest.approx(2.321928, abs=1e-4)


# --- bucket_field_values ------------------------------------------------------


def test_missing_values_form_their_own_bucket() -> None:
    counts = cig.bucket_field_values([1.0, 2.0, 3.0, None, None])
    assert cig.MISSING_BUCKET in counts
    assert counts[cig.MISSING_BUCKET] == 2


def test_continuous_numeric_field_is_quartile_bucketed() -> None:
    counts = cig.bucket_field_values([float(i) for i in range(100)])
    # 4 quartile buckets, no missing
    assert cig.MISSING_BUCKET not in counts
    assert set(counts) <= {"Q1", "Q2", "Q3", "Q4"}
    assert len(counts) == 4
    # roughly balanced -> close to the 2-bit maximum for 4 buckets
    assert cig.shannon_entropy(list(counts.values())) == pytest.approx(2.0, abs=0.05)


def test_booleans_are_categorical_not_bucketed() -> None:
    counts = cig.bucket_field_values([True, True, False, None])
    assert set(counts) == {"True", "False", cig.MISSING_BUCKET}


def test_low_cardinality_numeric_is_categorical() -> None:
    # only 2 distinct numeric values -> categorical, not quartiles
    counts = cig.bucket_field_values([1, 1, 1, 2, 2])
    assert set(counts) == {"1", "2"}


# --- get_dotted ---------------------------------------------------------------


def test_get_dotted_traverses_nested_dicts() -> None:
    record = {"specs": {"noise_db_indoor": 29}}
    assert cig.get_dotted(record, "specs.noise_db_indoor") == 29
    assert cig.get_dotted(record, "specs.missing") is None
    assert cig.get_dotted(record, "absent.path") is None


# --- smoke test against the real catalog (nice-to-have) -----------------------


@pytest.mark.skipif(not _MAY_LANH_DATA.exists(), reason="real catalog not present")
def test_may_lanh_information_gain_smoke() -> None:
    result = cig.compute_category("may_lanh")

    assert result["_meta"]["category_key"] == "may_lanh"
    assert result["_meta"]["n_records"] > 0
    assert isinstance(result["ranked_slots"], list)
    # uu_tien maps to real specs fields (inverter/energy_efficiency/noise) and
    # must be scored with a positive, finite entropy.
    assert "uu_tien" in result["ranked_slots"]
    uu = result["uu_tien"]
    assert uu["entropy"] > 0.0
    assert uu["n_samples"] == result["_meta"]["n_records"]
    # ranked_slots is sorted by entropy descending
    entropies = [result[name]["entropy"] for name in result["ranked_slots"]]
    assert entropies == sorted(entropies, reverse=True)
