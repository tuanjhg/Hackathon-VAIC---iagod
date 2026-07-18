"""Human-text normalization — teencode/abbreviation expansion and lightweight
misspelling correction, run as part of S1
(`docs/research/dmx-ai-workflow-v1.md` §3 "S1 — Tiền xử lý deterministic":
"từ điển ngành hàng dict tự xây + ViSoLex cho teencode chung").

Scope follows ADR C1 (`docs/research/dmx-tech-decisions.md`): "S1 chỉ làm việc
*chắc chắn đúng*; mọi thứ mơ hồ để LLM xử lý". Two confidence tiers reflect
this: entries in ``TEENCODE_DICT`` are common enough to expand unconditionally;
anything that only *fuzzy-matches* a vocabulary word is never silently
substituted — it is surfaced as a ``Correction`` with a confidence score so a
caller can decide to auto-apply (high confidence) or ask the customer instead
of guessing (medium confidence), per task 6's "hiểu ... hoặc hỏi lại nếu không
chắc chắn".
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

# Common Vietnamese chat/teencode shorthand -> canonical word. Deliberately
# small and unambiguous (no single-letter entries that collide with real
# words in this domain) so expansion never needs a confidence check.
TEENCODE_DICT: dict[str, str] = {
    "ko": "không",
    "hok": "không",
    "hong": "không",
    "khong": "không",
    "dc": "được",
    "đc": "được",
    "dk": "được",
    "ntn": "như thế nào",
    "sp": "sản phẩm",
    "sd": "sử dụng",
    "tvan": "tư vấn",
    "tv": "tư vấn",
    "bh": "bảo hành",
    "km": "khuyến mãi",
    "tgian": "thời gian",
    "nhiu": "nhiêu",
    "nhieu": "nhiêu",
    "bnhieu": "bao nhiêu",
    "bn": "bao nhiêu",
    "mn": "mọi người",
    "oke": "được",
    "okela": "được",
    "uk": "ừ",
    "ukm": "ừ",
    "vs": "với",
    "mik": "mình",
    "sag": "sang",
    "j": "gì",
    "z": "vậy",
}

# Curated single-word domain vocabulary for fuzzy typo correction (category
# terms + common brands seen in data/realdata). Callers extend this via the
# ``vocabulary`` parameter (e.g. preprocess.py adds category-dict tokens) --
# kept intentionally small here so a bad match against an unrelated word is
# unlikely.
DEFAULT_VOCABULARY: tuple[str, ...] = (
    "lạnh", "nóng", "mát", "đông", "giặt", "sấy", "rửa", "chén", "tủ", "máy",
    "bình", "điều", "hòa", "công", "suất", "dung", "tích", "inverter",
    "samsung", "lg", "panasonic", "daikin", "electrolux", "toshiba", "sharp",
    "casper", "midea", "aqua", "sanyo", "hitachi", "sunhouse", "ferroli",
)

_WORD_RE = re.compile(r"[^\s,.!?;:()\[\]\"'\-]+")

_HIGH_CONFIDENCE = 0.85
_ASK_CONFIDENCE = 0.72


@dataclass(frozen=True)
class Expansion:
    """A teencode token that was expanded unconditionally."""

    token: str
    expanded: str
    span: tuple[int, int]


@dataclass(frozen=True)
class Correction:
    """A token that only *fuzzy-matches* a vocabulary word.

    ``confidence >= 0.85`` is auto-applied into ``normalized``; the
    ``0.72–0.85`` band is reported but left untouched in the text, signalling
    the caller should ask rather than guess.
    """

    token: str
    suggestion: str
    confidence: float
    span: tuple[int, int]
    applied: bool


@dataclass(frozen=True)
class NormalizeResult:
    raw: str
    normalized: str
    expansions: list[Expansion] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)

    @property
    def needs_confirmation(self) -> bool:
        """True if any correction was too uncertain to auto-apply."""
        return any(not c.applied for c in self.corrections)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


_FOLD_SEP_RE = re.compile(r"[\s_-]+")


def fold_ascii(text: str) -> str:
    """ASCII-fold Vietnamese text into a canonical, accent-insensitive key.

    NFD-decompose and drop combining diacritics — mirroring ViSoLex's
    ``--rm_accent_ratio`` accent-removal preprocessing (HaDung2002/visolex) —
    then map ``đ``→``d`` (which NFD leaves intact), lowercase, and collapse runs
    of whitespace/underscore/hyphen to a single ``_``. So ``"Phòng ngủ"``,
    ``"phong ngu"`` and ``"phong_ngu"`` all fold to ``"phong_ngu"``.

    Used to match enum tokens the LLM emits in a non-canonical surface form
    against the ascii slot vocabulary, since the provider does not always
    enforce the guided-JSON schema (docs/pipelines.md §6.9).
    """
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)
    )
    folded = stripped.lower().replace("đ", "d")
    return _FOLD_SEP_RE.sub("_", folded.strip()).strip("_")


def normalize(
    text: str,
    *,
    vocabulary: Iterable[str] = DEFAULT_VOCABULARY,
    teencode_dict: dict[str, str] = TEENCODE_DICT,
) -> NormalizeResult:
    """Expand known teencode and flag/correct likely misspellings.

    Never mutates tokens that are not Vietnamese-diacritic-bearing lookalikes
    of a vocabulary word by a wide margin (``fuzzy_threshold`` below
    ``_ASK_CONFIDENCE`` is ignored entirely) -- code-switched English tokens
    ("inverter", "wifi", "gaming") simply never match this Vietnamese
    vocabulary and pass through untouched, satisfying "giữ code-switching"
    without special-casing.
    """
    raw = text
    vocab_lower = {word.lower() for word in vocabulary}
    result_chars = list(_nfc(text))
    expansions: list[Expansion] = []
    corrections: list[Correction] = []

    # Process right-to-left so earlier spans stay valid as we splice replacements in.
    matches = list(_WORD_RE.finditer(_nfc(text)))
    for m in reversed(matches):
        token = m.group(0)
        token_lower = token.lower()

        if token_lower in teencode_dict:
            expanded = teencode_dict[token_lower]
            expansions.append(Expansion(token=token, expanded=expanded, span=m.span()))
            result_chars[m.start() : m.end()] = list(expanded)
            continue

        if token_lower in vocab_lower or len(token) < 3:
            continue

        close = difflib.get_close_matches(token_lower, vocab_lower, n=1, cutoff=_ASK_CONFIDENCE)
        if not close:
            continue
        suggestion = close[0]
        confidence = difflib.SequenceMatcher(None, token_lower, suggestion).ratio()
        applied = confidence >= _HIGH_CONFIDENCE
        corrections.append(
            Correction(token=token, suggestion=suggestion, confidence=confidence, span=m.span(), applied=applied)
        )
        if applied:
            result_chars[m.start() : m.end()] = list(suggestion)

    expansions.reverse()
    corrections.reverse()
    return NormalizeResult(
        raw=raw, normalized="".join(result_chars), expansions=expansions, corrections=corrections
    )
