"""Human-text normalization tests (task 6) — teencode expansion and
confidence-tiered misspelling correction.
"""

from src.pipeline.humanize import fold_ascii, normalize


def test_fold_ascii_strips_diacritics_and_normalizes_separators() -> None:
    # Accent-, case- and separator-insensitive canonical key (ViSoLex-style
    # accent removal) so surface variants collapse to one comparison token.
    assert fold_ascii("Phòng ngủ") == "phong_ngu"
    assert fold_ascii("phong ngu") == "phong_ngu"
    assert fold_ascii("phong_ngu") == "phong_ngu"


def test_fold_ascii_handles_d_stroke_and_multiword() -> None:
    assert fold_ascii("Tủ Đông") == "tu_dong"
    assert fold_ascii("tiết kiệm điện") == "tiet_kiem_dien"


def test_teencode_expands_unconditionally() -> None:
    r = normalize("cho hỏi máy lạnh giá bao nhiêu, có bh ko")
    assert "bảo hành" in r.normalized
    assert "không" in r.normalized
    assert {e.token for e in r.expansions} == {"bh", "ko"}
    assert r.corrections == []
    assert not r.needs_confirmation


def test_multiple_abbreviations_in_one_sentence() -> None:
    r = normalize("sp này sd được lâu ko a")
    assert r.normalized == "sản phẩm này sử dụng được lâu không a"


def test_medium_confidence_typo_is_flagged_not_applied() -> None:
    r = normalize("máy lnah samsung giá nhiu")
    assert "lnah" in r.normalized  # not silently rewritten
    assert r.needs_confirmation
    correction = next(c for c in r.corrections if c.token == "lnah")
    assert correction.suggestion == "lạnh"
    assert not correction.applied
    assert 0.72 <= correction.confidence < 0.85


def test_high_confidence_typo_is_auto_applied() -> None:
    r = normalize("máy toshibaa hư rồi")
    assert "toshiba" in r.normalized
    assert "toshibaa" not in r.normalized
    correction = next(c for c in r.corrections if c.token == "toshibaa")
    assert correction.applied
    assert not r.needs_confirmation


def test_code_switched_english_untouched() -> None:
    r = normalize("máy lạnh inverter wifi smart")
    assert r.normalized == "máy lạnh inverter wifi smart"
    assert r.expansions == []
    assert r.corrections == []


def test_unrelated_text_produces_no_noise() -> None:
    r = normalize("hôm nay trời đẹp quá")
    assert r.normalized == "hôm nay trời đẹp quá"
    assert r.expansions == []
    assert r.corrections == []
