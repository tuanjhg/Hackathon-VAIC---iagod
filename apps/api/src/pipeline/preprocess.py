"""S1 — deterministic preprocessing (regex + dict, no LLM).

Per `docs/research/dmx-ai-workflow-v1.md` §3 "S1 — Tiền xử lý deterministic"
and ADR C1 (`docs/research/dmx-tech-decisions.md`): NFC normalize, category
dict, money parsing ("20 củ"/"20tr"/"hai chục triệu"), unit conversion
(HP↔BTU, m², lít) and code-switch preservation. Budget ~50ms
(`docs/pipelines.md` §6.1) — pure Python, no LLM call.

S1 only extracts what a rule can get *certainly right*
("S1 chỉ làm việc chắc chắn đúng ... mọi thứ mơ hồ để LLM xử lý", ADR C1); the
raw text always travels alongside the parsed result so S2 sees both.

Money/unit parsing covers shorthand (tr/củ/HP/lít/m²) as used in this domain,
not general free-form numeral parsing (e.g. thousands-separated raw VND
figures like "11.490.000đ" are out of scope for v0 — S2's guided_json extracts
those via the LLM instead).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from src.pipeline.humanize import NormalizeResult
from src.pipeline.humanize import normalize as humanize_normalize

# Ngành hàng dict: canonical category_key (matches data/realdata/processed
# category_key values) -> aliases/abbreviations seen in customer text. Bare
# 2-letter codes ("ml", "tl") are ambiguous in isolation by nature — S1 only
# proposes a hint; S2 (LLM, sees raw+normalized) has the final say.
CATEGORY_DICT: dict[str, tuple[str, ...]] = {
    "may_lanh": ("máy lạnh", "may lanh", "điều hòa", "dieu hoa", "ml"),
    "tu_lanh": ("tủ lạnh", "tu lanh", "tl"),
    "tu_mat_dong": ("tủ mát", "tủ đông", "tu mat", "tu dong", "tmd"),
    "may_nuoc_nong": (
        "máy nước nóng", "may nuoc nong", "bình nóng lạnh", "binh nong lanh", "mnn",
    ),
    "may_giat": ("máy giặt", "may giat", "mg"),
    "may_say": ("máy sấy", "may say"),
    "may_rua_chen": ("máy rửa chén", "may rua chen", "mrc"),
    "may_in": ("máy in", "may in"),
    "man_hinh": ("màn hình", "man hinh", "monitor"),
    "may_tinh_bang": ("máy tính bảng", "may tinh bang", "tablet"),
    "pc_de_ban": ("pc để bàn", "máy tính bàn", "may tinh ban", "pc de ban"),
    "dong_ho_tm": ("đồng hồ thông minh", "dong ho thong minh", "smartwatch"),
    "micro_karaoke": ("micro karaoke", "mic karaoke"),
    "micro_thu_am": ("micro thu âm", "micro thu am", "mic thu âm"),
}

_MONEY_UNIT_MULTIPLIER: dict[str, int] = {
    "triệu": 1_000_000, "tr": 1_000_000, "củ": 1_000_000,
    "nghìn": 1_000, "ngàn": 1_000, "k": 1_000,
}

_VN_DIGIT_WORDS: dict[str, int] = {
    "một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
}

# Rule-of-thumb HP->BTU step table as commonly marketed for split-unit air
# conditioners in VN (not a linear formula — capacities are conventionally
# rounded to these steps).
_HP_BTU_TABLE: dict[float, int] = {
    0.75: 6_000, 1.0: 9_000, 1.5: 12_000, 2.0: 18_000, 2.5: 21_000, 3.0: 24_000,
}

_NUM = r"\d+(?:[.,]\d+)?"
_VN_WORD_NUM = r"(?:một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười)(?:\s+(?:chục|trăm))?"
_AMOUNT = rf"(?:{_NUM}|{_VN_WORD_NUM})"
_UNIT = r"(?:triệu|tr|củ|nghìn|ngàn|k)\b"

_MONEY_RANGE_RE = re.compile(
    rf"(?P<lo>{_AMOUNT})\s*(?P<lo_unit>{_UNIT})?\s*(?:-|–|đến|tới)\s*"
    rf"(?P<hi>{_AMOUNT})\s*(?P<hi_unit>{_UNIT})",
    re.IGNORECASE,
)
_MONEY_UNIT_RE = re.compile(rf"(?P<amount>{_AMOUNT})\s*(?P<unit>{_UNIT})", re.IGNORECASE)
_MONEY_BARE_M_RE = re.compile(rf"\b(?P<amount>{_NUM})\s*m\b", re.IGNORECASE)

_AREA_RE = re.compile(rf"(?P<amount>{_NUM})\s*(?:m2|m²|mét\s*vuông|m\s*2)\b", re.IGNORECASE)
_HP_RE = re.compile(rf"(?P<amount>{_NUM})\s*(?:hp|ngựa|ngua)\b", re.IGNORECASE)
_LITER_RE = re.compile(rf"(?P<amount>{_NUM})\s*(?:lít|lit|l)\b", re.IGNORECASE)
_WATT_RE = re.compile(rf"(?P<amount>{_NUM})\s*(?:w|watt|watts)\b", re.IGNORECASE)

UnitKind = Literal["area_m2", "power_btu", "volume_liter", "power_watt"]


@dataclass(frozen=True)
class MoneyMatch:
    min_vnd: int
    max_vnd: int
    matched_text: str
    span: tuple[int, int]


@dataclass(frozen=True)
class UnitMatch:
    kind: UnitKind
    value: float
    matched_text: str
    span: tuple[int, int]


@dataclass(frozen=True)
class S1Result:
    raw: str
    normalized: str
    category_hint: str | None
    money: list[MoneyMatch] = field(default_factory=list)
    units: list[UnitMatch] = field(default_factory=list)
    humanize: NormalizeResult | None = None


def hp_to_btu(hp: float) -> int:
    """Convert HP ("ngựa") to BTU using the marketed step table, falling back
    to a linear scale (anchored at 1HP=9000 BTU) for values off the table.
    """
    if hp in _HP_BTU_TABLE:
        return _HP_BTU_TABLE[hp]
    closest = min(_HP_BTU_TABLE, key=lambda step: abs(step - hp))
    if abs(closest - hp) < 0.01:
        return _HP_BTU_TABLE[closest]
    return round(hp * 9_000)


def _parse_vn_number_words(phrase: str) -> float | None:
    """Parse "<digit-word> [chục|trăm]"-style phrases (e.g. "hai chục" -> 20).

    Narrow by design: covers the compound magnitude words this domain uses
    before a money unit ("hai chục triệu"), not general VN numeral grammar.
    """
    tokens = phrase.strip().lower().split()
    if not tokens or tokens[0] not in _VN_DIGIT_WORDS:
        return None
    digit = _VN_DIGIT_WORDS[tokens[0]]
    scale = 1
    for tok in tokens[1:]:
        if tok == "chục":
            scale *= 10
        elif tok == "trăm":
            scale *= 100
        else:
            return None
    return float(digit * scale)


def _amount_to_number(amount_str: str) -> float | None:
    amount_str = amount_str.strip()
    if re.fullmatch(_NUM, amount_str):
        return float(amount_str.replace(",", "."))
    return _parse_vn_number_words(amount_str)


def detect_category(text: str) -> str | None:
    """Return the first matching category_key, longest alias first so e.g.
    "tủ mát" is preferred over any shorter substring alias.
    """
    lowered = text.lower()
    all_aliases = [(alias, key) for key, aliases in CATEGORY_DICT.items() for alias in aliases]
    for alias, key in sorted(all_aliases, key=lambda pair: len(pair[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return key
    return None


def parse_money(text: str) -> list[MoneyMatch]:
    """Extract VND amounts, including ranges ("15-20tr") and bare-``m``
    slang ("20m" == 20 triệu). Money-``m`` never collides with area ``m²``:
    ``m2``/``m²`` leave no word boundary after ``m`` (digit/superscript
    immediately follows), so the bare-``m`` pattern structurally can't match
    inside them.
    """
    matches: list[MoneyMatch] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(span: tuple[int, int]) -> bool:
        return any(span[0] < c[1] and c[0] < span[1] for c in consumed)

    for m in _MONEY_RANGE_RE.finditer(text):
        lo = _amount_to_number(m.group("lo"))
        hi = _amount_to_number(m.group("hi"))
        unit = (m.group("hi_unit") or m.group("lo_unit") or "").lower()
        multiplier = _MONEY_UNIT_MULTIPLIER.get(unit)
        if lo is None or hi is None or multiplier is None:
            continue
        lo_vnd, hi_vnd = int(lo * multiplier), int(hi * multiplier)
        matches.append(
            MoneyMatch(min(lo_vnd, hi_vnd), max(lo_vnd, hi_vnd), m.group(0), m.span())
        )
        consumed.append(m.span())

    for m in _MONEY_UNIT_RE.finditer(text):
        if overlaps(m.span()):
            continue
        amount = _amount_to_number(m.group("amount"))
        multiplier = _MONEY_UNIT_MULTIPLIER.get(m.group("unit").lower())
        if amount is None or multiplier is None:
            continue
        vnd = int(amount * multiplier)
        matches.append(MoneyMatch(vnd, vnd, m.group(0), m.span()))
        consumed.append(m.span())

    for m in _MONEY_BARE_M_RE.finditer(text):
        if overlaps(m.span()):
            continue
        amount = _amount_to_number(m.group("amount"))
        if amount is None:
            continue
        vnd = int(amount * 1_000_000)
        matches.append(MoneyMatch(vnd, vnd, m.group(0), m.span()))
        consumed.append(m.span())

    matches.sort(key=lambda mm: mm.span[0])
    return matches


def parse_units(text: str) -> list[UnitMatch]:
    """Extract area (m²), power (HP→BTU), volume (lít) and wattage matches."""
    results: list[UnitMatch] = []
    for m in _AREA_RE.finditer(text):
        val = float(m.group("amount").replace(",", "."))
        results.append(UnitMatch("area_m2", val, m.group(0), m.span()))
    for m in _HP_RE.finditer(text):
        hp = float(m.group("amount").replace(",", "."))
        results.append(UnitMatch("power_btu", float(hp_to_btu(hp)), m.group(0), m.span()))
    for m in _LITER_RE.finditer(text):
        val = float(m.group("amount").replace(",", "."))
        results.append(UnitMatch("volume_liter", val, m.group(0), m.span()))
    for m in _WATT_RE.finditer(text):
        val = float(m.group("amount").replace(",", "."))
        results.append(UnitMatch("power_watt", val, m.group(0), m.span()))
    results.sort(key=lambda u: u.span[0])
    return results


def run_s1(text: str) -> S1Result:
    """Run the full S1 stage: humanize (task 6) then money/unit/category
    parsing (task 8) over the normalized text.
    """
    humanized = humanize_normalize(text)
    normalized = humanized.normalized
    return S1Result(
        raw=text,
        normalized=normalized,
        category_hint=detect_category(normalized),
        money=parse_money(normalized),
        units=parse_units(normalized),
        humanize=humanized,
    )
