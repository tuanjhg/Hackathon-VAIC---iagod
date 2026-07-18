"""Structural eval must use the same category keys as S1 and slot profiles."""

import pytest

from src.eval.structural import ConversationReport, aggregate, detect_golden_category


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tư vấn màn hình máy tính", "man_hinh"),
        ("Cần máy tính để bàn", "pc_de_ban"),
        ("Tìm máy tính bảng", "may_tinh_bang"),
        ("Mua máy in văn phòng", "may_in"),
        ("Đồng hồ thông minh cho bé", "dong_ho_tm"),
        ("Micro karaoke không dây", "micro_karaoke"),
        ("Micro thu âm cho iPhone", "micro_thu_am"),
    ],
)
def test_extended_catalog_categories_use_pipeline_keys(text: str, expected: str) -> None:
    assert detect_golden_category(text) == expected


def test_aggregate_separates_degraded_turns_from_errors() -> None:
    reports = [
        ConversationReport(
            id="c1",
            source="test",
            golden_category="may_giat",
            engaged_category="may_giat",
            supported=True,
            recommended=True,
            turn_kinds={"recommend": 1},
            degraded_turns=1,
            degraded_stages={"s2": 1, "s6": 1},
        )
    ]

    summary = aggregate(reports)

    assert summary["error_free_pct"] == 100.0
    assert summary["degraded_convs"] == 1
    assert summary["degraded_stage_distribution"] == {"s2": 1, "s6": 1}


def test_aggregate_reports_guardrail_and_latency_sla() -> None:
    report = ConversationReport(
        id="sla-1",
        source="synthetic",
        golden_category="may_giat",
        engaged_category="may_giat",
        supported=True,
        recommended=True,
        turn_kinds={"ask": 1, "recommend": 1},
        stage_latency_ms={"s2": [650.0, 420.0]},
        kind_latency_ms={"ask": [900.0], "recommend": [4_200.0]},
        post_guardrail_claims=4,
        post_guardrail_mismatches=0,
        post_guardrail_honesty_violations=0,
        honesty_opportunities=2,
        corrected_claims=1,
    )

    sla = aggregate([report])["sla"]

    assert sla["s2"]["p95_ms"] == 650.0
    assert sla["clarification"]["passes"] is True
    assert sla["recommendation"]["passes"] is True
    assert sla["guardrail"]["hallucination_rate_pct"] == 0.0
    assert sla["guardrail"]["honesty_recall_pct"] == 100.0
    assert sla["overall_passes"] is True
