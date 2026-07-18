"""S8 — respond: verdict enforcement, source panel, fallback table, PII mask.

Implements the response-side guardrail mechanics of
`docs/research/dmx-guardrail-design.md` §4 (hành động sau đối chiếu) and §7
(source log / privacy), turning S7's *report* into the *actions* the user
actually sees:

* **MISMATCH → sửa** (:func:`enforce`): the wrong number is replaced in place
  with the correct value rendered in the same unit — never a truncated
  sentence ("thay bằng giá trị đúng, không cắt cụt câu").
* **UNGROUNDED + no honesty phrase → cắt**: the whole sentence containing the
  offending claim is replaced with an explicit honesty line ("xóa mệnh đề +
  chèn câu honesty"). Cutting happens along :func:`src.verifier.sentence_spans`
  boundaries — the exact segmentation S7 judged honesty on.
* **Escalation input**: ``incident_count`` counts mismatches + honesty
  violations so the orchestrator can apply the ">2 incidents → regenerate
  once → fallback table" ladder (§4.6). The pure functions here never call an
  LLM themselves.
* **Fallback table** (:func:`render_fallback_table`): the never-fabricates
  last resort — a plain listing of the ranked candidates' real facts.
* **Source panel** (:func:`build_source_panel`): per-field provenance for the
  UI "Nguồn dữ liệu" panel (D3 pilot condition), reusing the facts tool's
  provenance for volatile fields and labelling spec fields as catalog data.
* **PII mask** (:func:`mask_pii`): phone/email → ``***`` before anything is
  written to the audit log (H3).

Pure functions only — no DB, no LLM, no I/O — so every guardrail action is
unit-testable in isolation, like S5/S7.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.pipeline.s5_ranking import RankingResult
from src.tools.price_promo_stock import ProductFacts
from src.verifier import ClaimVerdict, VerificationResult, sentence_spans

__all__ = [
    "MAX_INCIDENTS",
    "EnforcementResult",
    "SourceEntry",
    "VerifierFlag",
    "build_source_panel",
    "enforce",
    "field_label",
    "mask_pii",
    "render_fallback_table",
]

MAX_INCIDENTS = 2
"""Escalation threshold (guardrail doc §4.6): more than this many incidents in
one answer → the orchestrator regenerates once, then falls back to the table."""

# Vietnamese labels for honesty lines / fallback table rows. Mirrors the label
# vocabulary of s6_generate; kept local so S8 stays import-light and the label
# set can diverge (S8 labels name the *fact*, S6 labels name the *criterion*).
_FIELD_LABELS: dict[str, str] = {
    "price": "giá bán",
    "noise_db_indoor": "độ ồn",
    "noise_db": "độ ồn",
    "capacity_btu": "công suất làm lạnh",
    "energy_efficiency": "hiệu suất tiết kiệm điện",
    "energy_stars": "số sao tiết kiệm điện",
    "warranty_years_compressor": "bảo hành máy nén",
    "warranty_years": "bảo hành",
    "capacity_total_l": "dung tích",
    "capacity_l": "dung tích",
    "capacity_kg": "khối lượng giặt",
    "inverter": "công nghệ inverter",
    "power_watt": "công suất điện",
}

_PHONE_RE = re.compile(r"\b(?:\+?84|0)\d(?:[ .\-]?\d){7,9}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def field_label(field: str | None) -> str:
    """Vietnamese display label for a fact field (public: the chat service
    reuses the same vocabulary for card trade-off/strength text)."""
    if field is None:
        return "thông số"
    return _FIELD_LABELS.get(field, field)


def _fmt_number(value: int | float) -> str:
    return f"{value:g}"


def _fmt_vnd(value: int | float) -> str:
    return f"{int(value):,}".replace(",", ".") + "đ"


def _trim_trieu(value: int | float) -> str:
    amount = value / 1_000_000
    return f"{amount:g}"


class VerifierFlag(BaseModel):
    """One enforcement action taken on the prose — the ``verifier_flags`` the
    response/API surfaces (§6.10) so the UI can show what was sửa/cắt."""

    action: Literal["corrected", "removed"]
    sku: str | None = None
    field: str | None = None
    claimed_value: int | float | None = None
    actual_value: int | float | None = None


class EnforcementResult(BaseModel):
    """Outcome of :func:`enforce`.

    ``incident_count`` is the *pre-enforcement* tally (mismatches + honesty
    violations) — the escalation ladder compares it to :data:`MAX_INCIDENTS`
    regardless of how many edits were ultimately applied.
    """

    text: str
    flags: list[VerifierFlag] = Field(default_factory=list)
    incident_count: int = 0


# --------------------------------------------------------------------------- #
# Enforcement (sửa / cắt)                                                     #
# --------------------------------------------------------------------------- #
def _correction_text(claim: ClaimVerdict) -> str | None:
    """Render the correct value in the same unit as the matched fragment.

    Returns ``None`` when no faithful rendering exists (unknown field) — the
    claim then stays untouched rather than being rewritten into something the
    verifier grammar could not re-check.
    """
    actual = claim.actual_value
    if actual is None:
        return None
    if claim.kind == "derived":
        # Keep the comparator phrasing, swap only the amount ("3 triệu" → "2 triệu").
        # Marker digits ("[1]") can't collide: the pattern requires triệu/tr after.
        if claim.matched_text is None:
            return None
        return re.sub(
            r"\d+(?:[.,]\d+)?\s*(triệu|tr)\b",
            rf"{_trim_trieu(actual)} \1",
            claim.matched_text,
            count=1,
        )
    field = claim.field
    if field == "price":
        return _fmt_vnd(actual)
    if field in ("noise_db_indoor", "noise_db"):
        return f"{_fmt_number(actual)}dB"
    if field == "capacity_btu":
        return f"{_fmt_number(actual)} BTU"
    if field in ("warranty_years_compressor", "warranty_years"):
        return f"bảo hành {_fmt_number(actual)} năm"
    return None


def _honesty_line(claims: list[ClaimVerdict]) -> str:
    labels = sorted({field_label(c.field) for c in claims})
    subject = claims[0].marker or "sản phẩm này"
    return f"Hiện bên em chưa có dữ liệu về {', '.join(labels)} của {subject}."


def _sentence_of(spans: list[tuple[int, int]], pos: int) -> tuple[int, int] | None:
    for start, end in spans:
        if start <= pos < end:
            return (start, end)
    return None


def enforce(prose: str, verification: VerificationResult) -> EnforcementResult:
    """Apply S7's verdicts to ``prose``: correct mismatches in place, cut
    honesty-violating sentences, and report what was done.

    Edits are applied right-to-left so earlier spans stay valid. A correction
    whose claim sits inside a sentence already being removed is dropped (the
    sentence is gone); multiple violations in one sentence collapse into a
    single honesty line naming every missing field.
    """
    spans = sentence_spans(prose)

    removals: dict[tuple[int, int], list[ClaimVerdict]] = {}
    corrections: list[tuple[tuple[int, int], str, ClaimVerdict]] = []
    incidents = 0

    for claim in verification.claims:
        if claim.verdict == "mismatch":
            incidents += 1
            replacement = _correction_text(claim)
            if claim.span is not None and replacement is not None:
                corrections.append((claim.span, replacement, claim))
        elif claim.honesty_violation:
            incidents += 1
            if claim.span is not None:
                sentence = _sentence_of(spans, claim.span[0])
                if sentence is not None:
                    removals.setdefault(sentence, []).append(claim)

    flags: list[VerifierFlag] = []
    edits: list[tuple[int, int, str]] = []

    for (start, end), claims in removals.items():
        edits.append((start, end, " " + _honesty_line(claims) if start > 0 else _honesty_line(claims)))
        for claim in claims:
            flags.append(
                VerifierFlag(
                    action="removed",
                    sku=claim.sku,
                    field=claim.field,
                    claimed_value=claim.claimed_value,
                    actual_value=None,
                )
            )

    removed_ranges = list(removals)
    for (start, end), replacement, claim in corrections:
        if any(r_start <= start < r_end for r_start, r_end in removed_ranges):
            continue  # its sentence is being cut anyway
        edits.append((start, end, replacement))
        flags.append(
            VerifierFlag(
                action="corrected",
                sku=claim.sku,
                field=claim.field,
                claimed_value=claim.claimed_value,
                actual_value=claim.actual_value,
            )
        )

    text = prose
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + replacement + text[end:]

    return EnforcementResult(text=text.strip(), flags=flags, incident_count=incidents)


# --------------------------------------------------------------------------- #
# Source panel (guardrail Tầng 5, pilot condition D3)                         #
# --------------------------------------------------------------------------- #
class SourceEntry(BaseModel):
    """One (SKU, field) → provenance row of the UI "Nguồn dữ liệu" panel."""

    sku: str
    field: str
    dataset: str
    fetched_at: str | None = None


def build_source_panel(
    s7_facts: dict[str, dict[str, Any]],
    facts_by_sku: dict[str, ProductFacts | None],
) -> list[SourceEntry]:
    """Provenance rows for every fact the turn actually had available.

    Volatile fields (``price``) reuse the facts tool's own provenance; spec
    fields are labelled ``catalog_snapshot`` (their provenance lives in the
    catalog ETL, not per-request). ``None`` values are skipped — a missing
    fact is surfaced by the honesty layer, not cited as a source.
    """
    entries: list[SourceEntry] = []
    for sku in sorted(s7_facts):
        product_facts = facts_by_sku.get(sku)
        for field, value in s7_facts[sku].items():
            if value is None:
                continue
            if field == "price" and product_facts is not None:
                entries.append(
                    SourceEntry(
                        sku=sku,
                        field=field,
                        dataset=product_facts.sale_price.source.get("dataset", "unknown"),
                        fetched_at=product_facts.sale_price.fetched_at,
                    )
                )
            else:
                entries.append(SourceEntry(sku=sku, field=field, dataset="catalog_snapshot"))
    return entries


# --------------------------------------------------------------------------- #
# Fallback table (đường lui không bao giờ bịa)                                #
# --------------------------------------------------------------------------- #
def render_fallback_table(
    ranking: RankingResult, candidates: list[dict[str, Any]]
) -> str:
    """Compact listing of top candidates, zero generation.

    Used when even the regenerated answer exceeds :data:`MAX_INCIDENTS` — the
    reply degrades to deterministic candidate names instead of prose. Detailed
    facts stay in the structured cards/source panel, avoiding an unreadable
    mobile message that duplicates every raw catalog field.
    """
    by_sku = {str(c.get("sku")): c for c in candidates}
    rows: list[str] = []
    for index, breakdown in enumerate(ranking.top, start=1):
        cand = by_sku.get(breakdown.sku, {})
        name = str(cand.get("name", breakdown.sku))
        price = cand.get("price")
        parts = [
            f"{field_label('price')}: {_fmt_vnd(price) if price is not None else 'chưa có dữ liệu'}"
        ]
        first_spec = next(
            (
                (field, value)
                for field, value in (cand.get("specs") or {}).items()
                if value is not None
            ),
            None,
        )
        if first_spec is not None:
            field, value = first_spec
            parts.append(f"{field_label(field)}: {value}")
        rows.append(f"[{index}] {name} — " + "; ".join(parts))
    return (
        "Dạ dưới đây là các lựa chọn được xếp hạng bằng số liệu trực tiếp từ hệ thống. "
        "Anh/chị có thể xem giá, điểm phù hợp và điều cần cân nhắc trên từng thẻ.\n"
        + "\n".join(rows)
    )


# --------------------------------------------------------------------------- #
# PII mask (guardrail Tầng 5, H3)                                             #
# --------------------------------------------------------------------------- #
def mask_pii(text: str) -> str:
    """Mask phone numbers and emails with ``***`` before logging."""
    masked = _EMAIL_RE.sub("***", text)
    return _PHONE_RE.sub("***", masked)
