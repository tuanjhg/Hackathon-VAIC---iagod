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
