"""S7 — per-claim verifier (Tầng 2 guardrail, ADR C6).

Per `docs/research/dmx-guardrail-design.md` §4 "Tầng 2 — Verifier" and
`docs/pipelines.md` §6.7/§6.1 "S7": after S6 generates advisory prose, S7 tears
it back down into atomic number+unit claims and checks each one against the
turn's ``facts`` JSON — the same structure S4/S5/S6 already treat as the single
source of truth. Pure function, no DB/LLM/I/O, so it runs alongside the S6
token stream without adding latency to TTFT (~200ms budget, `docs/pipelines.md`
§6.9).

Contract with S6 (`src.pipeline.s6_generate.GeneratedAdvice`): prose refers to
products only via ``[1]``/``[2]``/``[3]``/``[A]`` markers, never bare names —
``marker_map`` (also produced by S6) resolves each marker back to a SKU.

Claim kinds:

* **direct** — a number bound to one SKU's own fact (độ ồn, BTU, giá, bảo hành).
  Checked by exact lookup in ``facts[sku]``: present + equal -> ``match``;
  present + different -> ``mismatch``; absent -> ``unverifiable`` (never
  fabricated — "null is null" per guardrail Tầng 0).
* **derived** — a computed difference ("rẻ hơn/đắt hơn N triệu", ADR C6 4b).
  This number legitimately does NOT appear verbatim in ``facts`` — the verifier
  *recomputes* it from the two SKUs' own ``price`` and compares, rather than
  string-matching, so the comparison feature itself is never false-flagged.

Out of scope for this pass (documented, not silently dropped): percentage-based
derived claims ("tiết kiệm 15%") and TCO-tool-result claims (guardrail doc 4b) —
both need a documented base/tool-result to recompute against that isn't part of
this contract yet. Free-text advisory claims ("chạy êm", "phù hợp phòng ngủ")
are deliberately never enforced here either (guardrail doc §4 point 4: blocking
a correct judgment call would maim an otherwise-good answer) — the verifier
only constrains product facts, never opinion.

Also implements the two guardrail checks layered on top of claim verification:

* **Honesty (Tầng 3, STT34)**: a claim that names a concrete value for a field
  genuinely absent from a *known* SKU's facts is a violation unless the
  sentence already owns up to the gap (an "honesty phrase" like "chưa có dữ
  liệu").
* **Freshness (Tầng 3, STT35)**: any SKU referenced by a claim whose
  ``fetched_at`` snapshot is older than ``freshness_threshold_hours`` is
  flagged.

``per_claim_error_rate`` (guardrail Tầng 6 metric) = mismatches / total claims —
the number the guardrail demo has to show live, not just describe.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "DEFAULT_FRESHNESS_THRESHOLD_HOURS",
    "ClaimVerdict",
    "VerificationResult",
    "sentence_spans",
    "verify",
]

DEFAULT_FRESHNESS_THRESHOLD_HOURS = 24.0

# Field candidates per unit, tried in order against `facts[sku]` — the reverse
# of s6_generate.GLOSSARY (field name -> phrase): prose only carries the unit,
# not the original catalog key, so a unit maps back to one or more candidate
# fact keys. First present (non-None) wins; if none is present, the first
# candidate is kept as the informational label on the unverifiable claim.
_NOISE_FIELDS: tuple[str, ...] = ("noise_db_indoor", "noise_db")
_BTU_FIELDS: tuple[str, ...] = ("capacity_btu",)
_WARRANTY_FIELDS: tuple[str, ...] = ("warranty_years_compressor", "warranty_years")
_PRICE_FIELDS: tuple[str, ...] = ("price",)

_HONESTY_PHRASES: tuple[str, ...] = (
    "chưa có dữ liệu",
    "chưa có thông tin",
    "chưa chắc chắn",
    "chưa xác nhận",
    "không chắc",
    "chưa rõ",
)

# --------------------------------------------------------------------------- #
# Claim extraction pattern.                                                   #
#                                                                              #
# One combined regex rather than separate per-unit passes: binding a claim to #
# "the nearest preceding marker" needs a single left-to-right scan that       #
# interleaves marker tokens and value tokens in true document order — running #
# each pattern as its own pass (then merging) would lose that order.          #
#                                                                              #
# Alternatives are tried left-to-right *at each scan position* (Python `re`   #
# alternation picks the first that matches, not the longest), so the          #
# two-marker comparator must precede the bare single-marker token, or "[1]"   #
# alone would win before "rẻ hơn [2] ..." is ever attempted.                  #
# --------------------------------------------------------------------------- #
_CHEAPER_FRAG = (
    r"\[(?P<cmp_a>[^\]\s]+)\]\s*(?P<cmp_word>rẻ\s+hơn|đắt\s+hơn)\s+"
    r"\[(?P<cmp_b>[^\]\s]+)\]\s*(?P<cmp_amt>\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b"
)
# Glued shorthand "17tr99" == 17_990_000 — no space allowed, unlike plain "N tr".
_GLUED_MONEY_FRAG = r"(?P<glued_amt>\d+(?:[.,]\d+)?)tr(?P<glued_sub>\d{2})\b"
_CURRENCY_FRAG = r"(?P<cur_amt>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:đ|₫|vnđ|vnd)\b"
_TRIEU_FRAG = r"(?P<tri_amt>\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b"
_WARRANTY_FRAG = r"bảo\s+hành\s+(?P<war_amt>\d+(?:[.,]\d+)?)\s*năm\b"
_NOISE_FRAG = r"(?P<noise_amt>\d+(?:[.,]\d+)?)\s*dB\b"
_BTU_FRAG = r"(?P<btu_amt>\d+(?:[.,]\d+)?)\s*BTU\b"
_MARKER_FRAG = r"(?P<marker_tok>\[[^\]\s]+\])"

_CLAIM_RE = re.compile(
    "|".join(
        [
            _CHEAPER_FRAG,
            _GLUED_MONEY_FRAG,
            _CURRENCY_FRAG,
            _TRIEU_FRAG,
            _WARRANTY_FRAG,
            _NOISE_FRAG,
            _BTU_FRAG,
            _MARKER_FRAG,
        ]
    ),
    re.IGNORECASE,
)


class ClaimVerdict(BaseModel):
    """One atomic claim extracted from S6 prose, checked against ``facts``.

    ``field`` is always populated — even on an ``unverifiable`` claim — with
    the best-candidate fact key for that unit/phrase, so audit logging always
    has something to point at. ``span``/``matched_text`` locate the claim in
    the prose (S8 needs them to rewrite/cut in place); ``honesty_violation``
    is the per-claim form of ``VerificationResult.honesty_violations`` so S8
    can act on exactly the offending claim.
    """

    kind: Literal["direct", "derived"]
    verdict: Literal["match", "mismatch", "unverifiable"]
    sku: str | None = None
    marker: str | None = None
    field: str | None = None
    claimed_value: int | float | None = None
    actual_value: int | float | None = None
    span: tuple[int, int] | None = None
    matched_text: str | None = None
    honesty_violation: bool = False


class VerificationResult(BaseModel):
    claims: list[ClaimVerdict] = Field(default_factory=list)
    per_claim_error_rate: float = 0.0
    honesty_violations: list[str] = Field(default_factory=list)
    freshness_flags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Number parsing helpers                                                      #
# --------------------------------------------------------------------------- #
def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _clean_num(value: float | int) -> int | float:
    return int(value) if float(value).is_integer() else value


def _digits_only_int(text: str) -> int:
    return int(re.sub(r"[.,]", "", text))


def _direct_value(gd: dict[str, str | None]) -> tuple[tuple[str, ...], int | float]:
    """Resolve a matched direct-claim group set to (candidate fields, claimed value).

    Exactly one of these groups is set whenever this is called (the caller
    already ruled out ``marker_tok``/``cmp_amt``) — the alternation guarantees
    mutual exclusivity. The two ``assert``s document that invariant for the
    type checker (regex co-occurrence isn't something mypy can see): the
    ``glued`` pair are always captured together, and if none of the named
    branches matched, ``btu_amt`` is the only alternative left.
    """
    if (glued_amt := gd["glued_amt"]) is not None:
        glued_sub = gd["glued_sub"]
        assert glued_sub is not None
        return _PRICE_FIELDS, int(_num(glued_amt)) * 1_000_000 + int(glued_sub) * 10_000
    if (cur_amt := gd["cur_amt"]) is not None:
        return _PRICE_FIELDS, _digits_only_int(cur_amt)
    if (tri_amt := gd["tri_amt"]) is not None:
        return _PRICE_FIELDS, _clean_num(_num(tri_amt) * 1_000_000)
    if (war_amt := gd["war_amt"]) is not None:
        return _WARRANTY_FIELDS, _clean_num(_num(war_amt))
    if (noise_amt := gd["noise_amt"]) is not None:
        return _NOISE_FIELDS, _clean_num(_num(noise_amt))
    btu_amt = gd["btu_amt"]
    assert btu_amt is not None
    return _BTU_FIELDS, _clean_num(_num(btu_amt))


# --------------------------------------------------------------------------- #
# Fact resolution                                                             #
# --------------------------------------------------------------------------- #
def _resolve_direct(
    sku: str | None,
    candidates: tuple[str, ...],
    claimed: int | float,
    facts: dict[str, dict[str, Any]],
) -> tuple[str, int | float | None, Literal["match", "mismatch", "unverifiable"]]:
    sku_facts: dict[str, Any] = facts.get(sku, {}) if sku is not None else {}
    field = next((f for f in candidates if sku_facts.get(f) is not None), candidates[0])
    actual = sku_facts.get(field)
    if actual is None:
        return field, None, "unverifiable"
    if actual == claimed:
        return field, actual, "match"
    return field, actual, "mismatch"


def _resolve_derived(
    cheaper: bool,
    sku_a: str | None,
    sku_b: str | None,
    claimed: int | float,
    facts: dict[str, dict[str, Any]],
) -> tuple[int | float | None, Literal["match", "mismatch", "unverifiable"]]:
    if sku_a is None or sku_b is None:
        return None, "unverifiable"
    price_a = facts.get(sku_a, {}).get("price")
    price_b = facts.get(sku_b, {}).get("price")
    if price_a is None or price_b is None:
        return None, "unverifiable"
    actual = _clean_num((price_b - price_a) if cheaper else (price_a - price_b))
    return actual, ("match" if actual == claimed else "mismatch")


# --------------------------------------------------------------------------- #
# Sentence segmentation (for the honesty-phrase check; public because S8     #
# must cut along the exact same boundaries S7 judged honesty on)             #
# --------------------------------------------------------------------------- #
def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for m in re.finditer(r"[.!?]+", text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _sentence_containing(text: str, spans: list[tuple[int, int]], pos: int) -> str:
    for start, end in spans:
        if start <= pos < end:
            return text[start:end]
    return text[spans[-1][0] :] if spans else text


def _has_honesty_phrase(sentence: str) -> bool:
    low = sentence.lower()
    return any(phrase in low for phrase in _HONESTY_PHRASES)


# --------------------------------------------------------------------------- #
# Public entry point                                                         #
# --------------------------------------------------------------------------- #
def verify(
    prose: str,
    marker_map: dict[str, str],
    facts: dict[str, dict[str, Any]],
    fetched_at: dict[str, str] | None = None,
    freshness_threshold_hours: float = DEFAULT_FRESHNESS_THRESHOLD_HOURS,
) -> VerificationResult:
    """Run S7: extract atomic claims from ``prose`` and check each against
    ``facts``, plus the honesty and freshness guardrail checks.

    ``marker_map`` and ``facts`` are exactly S6's ``GeneratedAdvice.marker_map``
    and the turn's ``facts`` JSON (S4/S5's shared source of truth) — this
    function takes plain dicts rather than those types so it has zero import
    coupling to the rest of the pipeline and stays trivially unit-testable.
    """
    spans = sentence_spans(prose)
    claims: list[ClaimVerdict] = []
    honesty_violations: list[str] = []
    current_marker: str | None = None
    current_sku: str | None = None

    for m in _CLAIM_RE.finditer(prose):
        gd = m.groupdict()

        if gd["marker_tok"] is not None:
            current_marker = gd["marker_tok"]
            current_sku = marker_map.get(current_marker)
            continue

        claim: ClaimVerdict
        if gd["cmp_amt"] is not None:
            marker_a, marker_b = f"[{gd['cmp_a']}]", f"[{gd['cmp_b']}]"
            sku_a, sku_b = marker_map.get(marker_a), marker_map.get(marker_b)
            cheaper = gd["cmp_word"].lower().startswith("rẻ")
            claimed = _clean_num(_num(gd["cmp_amt"]) * 1_000_000)
            actual, verdict = _resolve_derived(cheaper, sku_a, sku_b, claimed, facts)
            claim = ClaimVerdict(
                kind="derived",
                verdict=verdict,
                sku=sku_a,
                marker=marker_a,
                field=_PRICE_FIELDS[0],
                claimed_value=claimed,
                actual_value=actual,
                span=m.span(),
                matched_text=m.group(0),
            )
            current_marker, current_sku = marker_b, sku_b
        else:
            candidates, claimed = _direct_value(gd)
            field, actual, verdict = _resolve_direct(current_sku, candidates, claimed, facts)
            claim = ClaimVerdict(
                kind="direct",
                verdict=verdict,
                sku=current_sku,
                marker=current_marker,
                field=field,
                claimed_value=claimed,
                actual_value=actual,
                span=m.span(),
                matched_text=m.group(0),
            )

        claims.append(claim)

        if claim.sku is not None and claim.verdict == "unverifiable":
            sentence = _sentence_containing(prose, spans, m.start())
            if not _has_honesty_phrase(sentence):
                claim.honesty_violation = True
                honesty_violations.append(
                    f"{claim.sku}: nêu giá trị cụ thể cho '{claim.field}' nhưng dữ liệu "
                    "không có (honesty check, STT34)"
                )

    mismatches = sum(1 for c in claims if c.verdict == "mismatch")
    error_rate = mismatches / len(claims) if claims else 0.0

    freshness_flags: list[str] = []
    if fetched_at:
        now = datetime.now(UTC)
        referenced_skus = sorted({c.sku for c in claims if c.sku is not None})
        for sku in referenced_skus:
            ts = fetched_at.get(sku)
            if ts is None:
                continue
            age_hours = (now - datetime.fromisoformat(ts)).total_seconds() / 3600
            if age_hours > freshness_threshold_hours:
                freshness_flags.append(
                    f"{sku}: dữ liệu lấy lúc {ts}, đã quá {freshness_threshold_hours:.0f}h "
                    "(freshness check, STT35)"
                )

    return VerificationResult(
        claims=claims,
        per_claim_error_rate=error_rate,
        honesty_violations=honesty_violations,
        freshness_flags=freshness_flags,
    )
