"""S8 tests — enforcement (sửa/cắt), source panel, fallback table, PII mask.

Enforcement fixtures run the *real* S7 :func:`~src.verifier.verify` over
hand-built prose so the span/honesty contract between the two stages is
exercised, not simulated.
"""

from typing import Any

from src.pipeline.s5_ranking import RankingResult, ScoreBreakdown
from src.pipeline.s8_respond import (
    MAX_INCIDENTS,
    build_source_panel,
    enforce,
    mask_pii,
    render_fallback_table,
)
from src.tools.price_promo_stock import Fact, ProductFacts
from src.verifier import verify

MARKER_MAP: dict[str, str] = {"[1]": "sku_a", "[2]": "sku_b", "[3]": "sku_c"}

FACTS: dict[str, dict[str, Any]] = {
    "sku_a": {
        "noise_db_indoor": 29,
        "price": 15_990_000,
        "warranty_years_compressor": 10,
    },
    "sku_b": {"noise_db_indoor": 31, "price": 17_990_000},
    "sku_c": {"price": 13_990_000},  # no noise / no warranty
}


def _enforced(prose: str) -> tuple[str, Any]:
    result = enforce(prose, verify(prose, MARKER_MAP, FACTS))
    return result.text, result


# --------------------------------------------------------------------------- #
# MISMATCH → sửa (replace in place, same unit)                                #
# --------------------------------------------------------------------------- #
def test_wrong_noise_is_corrected_in_place() -> None:
    text, result = _enforced("[1] có độ ồn 25dB.")
    assert text == "[1] có độ ồn 29dB."
    assert result.incident_count == 1
    assert [f.action for f in result.flags] == ["corrected"]
    assert result.flags[0].claimed_value == 25 and result.flags[0].actual_value == 29


def test_wrong_price_is_corrected_with_vnd_formatting() -> None:
    text, _ = _enforced("[1] giá 14.990.000đ.")
    assert "15.990.000đ" in text
    assert "14.990.000đ" not in text


def test_wrong_derived_difference_swaps_only_the_amount() -> None:
    text, result = _enforced("[1] rẻ hơn [2] 3 triệu.")
    assert text == "[1] rẻ hơn [2] 2 triệu."
    assert result.flags[0].action == "corrected"


def test_correct_claims_are_left_untouched() -> None:
    prose = "[1] có độ ồn 29dB, giá 15.990.000đ."
    text, result = _enforced(prose)
    assert text == prose
    assert result.flags == []
    assert result.incident_count == 0


# --------------------------------------------------------------------------- #
# UNGROUNDED + no honesty phrase → cắt (sentence replaced by honesty line)   #
# --------------------------------------------------------------------------- #
def test_ungrounded_sentence_is_cut_and_replaced_with_honesty_line() -> None:
    text, result = _enforced("[3] phù hợp ngân sách. [3] bảo hành 10 năm.")
    assert "10 năm" not in text
    assert text.startswith("[3] phù hợp ngân sách.")
    assert "chưa có dữ liệu về bảo hành máy nén của [3]" in text
    assert [f.action for f in result.flags] == ["removed"]
    assert result.incident_count == 1


def test_honest_sentence_is_not_cut() -> None:
    prose = "[3] bảo hành 10 năm nhưng chưa có dữ liệu chính thức."
    text, result = _enforced(prose)
    assert text == prose
    assert result.incident_count == 0


def test_correction_inside_removed_sentence_is_dropped() -> None:
    # One sentence, two incidents: a noise mismatch (31 real) and a warranty
    # honesty violation on sku_b → the sentence is cut once; no stray edit.
    text, result = _enforced("[2] có độ ồn 25dB, bảo hành 10 năm.")
    assert "25dB" not in text and "10 năm" not in text
    assert "chưa có dữ liệu" in text
    assert [f.action for f in result.flags] == ["removed"]
    assert result.incident_count == 2


def test_incident_count_feeds_escalation_threshold() -> None:
    _, result = _enforced("[1] có độ ồn 20dB. [1] giá 9.990.000đ. [2] có độ ồn 20dB.")
    assert result.incident_count == 3
    assert result.incident_count > MAX_INCIDENTS


# --------------------------------------------------------------------------- #
# Source panel                                                                #
# --------------------------------------------------------------------------- #
def _product_facts(sku: str, sale_price: int | None) -> ProductFacts:
    def fact(field: str, value: Any) -> Fact:
        return Fact(
            value=value,
            source={"dataset": "may_lanh", "row": sku, "field": field},
            fetched_at="2026-07-18T09:00:00+00:00",
        )

    return ProductFacts(
        sku=sku,
        original_price=fact("original_price", None),
        sale_price=fact("sale_price", sale_price),
        promotions=fact("promotions", []),
        stock=Fact(
            value=None,
            source={"dataset": "unavailable", "row": sku, "field": "stock"},
            fetched_at="2026-07-18T09:00:00+00:00",
        ),
    )


def test_source_panel_uses_tool_provenance_for_price_and_skips_nulls() -> None:
    s7_facts = {
        "sku_a": {"noise_db_indoor": 29, "price": 15_990_000, "gas_type": None},
        "sku_c": {"price": None},
    }
    panel = build_source_panel(s7_facts, {"sku_a": _product_facts("sku_a", 15_990_000)})

    by_key = {(e.sku, e.field): e for e in panel}
    assert by_key[("sku_a", "price")].dataset == "may_lanh"
    assert by_key[("sku_a", "price")].fetched_at == "2026-07-18T09:00:00+00:00"
    assert by_key[("sku_a", "noise_db_indoor")].dataset == "catalog_snapshot"
    # Null facts are honesty-layer business, never cited as sources.
    assert ("sku_a", "gas_type") not in by_key
    assert ("sku_c", "price") not in by_key


def test_source_panel_can_limit_recommendation_sources() -> None:
    facts = {
        "sku_a": {"capacity_btu": 12000, "inverter": True, "noise_db_indoor": 29,
                  "energy_efficiency": 6.2, "made_in": "Vietnam", "price": 15_990_000},
        "sku_b": {"capacity_btu": 9000, "price": 10_000_000},
    }
    panel = build_source_panel(
        facts,
        {"sku_a": _product_facts("sku_a", 15_990_000)},
        skus=["sku_a"],
        max_fields_per_sku=4,
    )

    assert len(panel) == 4
    assert panel[0].field == "price"
    assert {entry.sku for entry in panel} == {"sku_a"}


# --------------------------------------------------------------------------- #
# Fallback table                                                              #
# --------------------------------------------------------------------------- #
def test_fallback_table_lists_real_facts_and_admits_missing_price() -> None:
    ranking = RankingResult(
        top=[
            ScoreBreakdown(sku="sku_a", total_score=1.0, price=15_990_000),
            ScoreBreakdown(sku="sku_c", total_score=0.2, price=None),
        ]
    )
    candidates = [
        {"sku": "sku_a", "name": "Panasonic A", "price": 15_990_000,
         "specs": {"noise_db_indoor": 29, "gas_type": None}},
        {"sku": "sku_c", "name": "Casper C", "price": None, "specs": {}},
    ]
    table = render_fallback_table(ranking, candidates)
    assert "[1] Panasonic A" in table and "[2] Casper C" in table
    assert "15.990.000đ" in table
    assert "độ ồn: 29" in table
    assert "chưa có dữ liệu" in table  # sku_c price
    assert "gas_type" not in table  # null spec skipped


# --------------------------------------------------------------------------- #
# PII mask                                                                    #
# --------------------------------------------------------------------------- #
def test_mask_pii_masks_phones_and_emails_but_not_prices() -> None:
    masked = mask_pii("Gọi em 0912 345 678 hoặc mail a.b+c@example.com, giá 15.990.000đ")
    assert "0912" not in masked
    assert "example.com" not in masked
    assert masked.count("***") == 2
    assert "15.990.000đ" in masked
