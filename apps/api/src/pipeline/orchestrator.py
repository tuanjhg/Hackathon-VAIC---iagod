"""Orchestrator — wires S1→S7 into one advisory turn (nhánh ``tư_vấn``, ADR A1).

Per ``docs/pipelines.md`` §6.1 and the ProductAgent reference notes
(`docs/research/dmx-productagent-reference.md` §5.1), the per-turn order is:

    S1 (normalize) → S2 (intent+slot, merge) → S4-prefilter (count+candidates)
      → S3 (ask | proceed) → [ask: deterministic question]
                             [proceed: facts → S5 → S6 → S7]

The **prefilter runs before S3 on every turn** — S3's ``candidate_count`` input
comes from the actual filtered catalog, and clarifying questions are grounded
in what is really available (the ProductAgent ablation result), not in a
linear reading of the S1→S8 diagram.

Scope of this v1 (each boundary is deliberate, not an accident):

* Only the ``tu_van`` intent gets the full pipeline. ``ngoai_pham_vi`` gets the
  polite refusal; ``policy_faq`` / ``so_sanh_truc_tiep`` / ``hoi_chi_tiet_sp``
  get an honest "chưa hỗ trợ" stub until their branches are built.
* Clarifying questions are deterministic (slot YAML ``sample_question`` joined,
  ≤ ``MAX_ASK_BATCH`` per message) — no LLM call on the ask path, so the
  hỏi-ngược flow is explainable and its latency is just S2.
  ``quick_replies`` carries the first asked slot's enum ``values`` verbatim
  (raw tokens; humanizing them is presentation-layer work).
* S7's verdicts are **enforced** through S8 (guardrail doc §4): mismatches are
  corrected in place, honesty-violating sentences cut, and the escalation
  ladder applies — more than :data:`~src.pipeline.s8_respond.MAX_INCIDENTS`
  incidents regenerates S6 once with specific error feedback; a still-bad
  retry degrades to the never-fabricates fallback table. What was done is
  reported via ``verifier_flags``; provenance via ``source_panel``.
* Streaming is not wired here; ``run_turn`` returns one complete result. The
  SSE endpoint slices it later without changing this module's contract.

Like the stage modules, this is DB/framework-free: the catalog retriever and
the price/promo/stock tool arrive by dependency injection (protocols below),
so tests drive the whole turn with fakes and no SQLAlchemy session. ``profile``
is **mutated in place** (merge/ask/assumption bookkeeping) and also returned on
the result — callers persist it via their ``SessionStore``.

Facts discipline (guardrail Tầng 0): candidate ``price``/``in_stock`` are
overwritten from the price_promo_stock tool — the serving source of truth for
volatile fields — never from the catalog snapshot the SQL filter used. A SKU
the facts tool does not know keeps ``price=None`` (absence is not a price).
"""

from __future__ import annotations

import time
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from src.pipeline.need_profile import NeedProfile
from src.pipeline.preprocess import run_s1
from src.pipeline.s2_extract import S2Result, extract
from src.pipeline.s3_policy import PolicyDecision, decide_policy
from src.pipeline.s5_ranking import BUDGET_SLOT_NAME, RankingResult, rank_candidates
from src.pipeline.s6_generate import GeneratedAdvice, generate
from src.pipeline.s8_respond import (
    MAX_INCIDENTS,
    SourceEntry,
    VerifierFlag,
    build_source_panel,
    enforce,
    render_fallback_table,
)
from src.pipeline.slots import available_categories, load_slot_profile
from src.tools.price_promo_stock import ProductFacts
from src.verifier import VerificationResult, verify

__all__ = [
    "DEFAULT_RETRIEVE_LIMIT",
    "CandidateRetriever",
    "FactsToolLike",
    "LLMRouterLike",
    "RetrievalResult",
    "TurnResult",
    "run_turn",
]

DEFAULT_RETRIEVE_LIMIT = 20
"""Candidates fetched per prefilter — matches S3's ``HIGH_CANDIDATE_THRESHOLD``
(above it the turn asks instead of ranking, so more rows are never needed)."""

_ASK_CATEGORY_MESSAGE = (
    "Dạ anh/chị đang cần tư vấn sản phẩm nào ạ? Em hỗ trợ tốt nhất các ngành bên dưới."
)
_NO_RESULTS_MESSAGE = (
    "Dạ hiện em chưa tìm được sản phẩm phù hợp với đúng nhu cầu này trong dữ liệu. "
    "Anh/chị có muốn nới ngân sách hoặc điều chỉnh một chút để em tìm lại không ạ?"
)
_OUT_OF_SCOPE_MESSAGE = (
    "Dạ em là trợ lý tư vấn điện máy nên câu này em xin phép không trả lời ạ. "
    "Anh/chị đang cần tìm sản phẩm nào để em hỗ trợ mình liền ạ?"
)
_UNSUPPORTED_MESSAGE = (
    "Dạ phần này em đang được hoàn thiện nên chưa hỗ trợ được ngay ạ. "
    "Anh/chị cần tư vấn chọn sản phẩm thì em giúp được liền!"
)


class LLMRouterLike(Protocol):
    """Structural type for anything with the router's ``complete`` coroutine
    (same shape S2/S6 declare — one definition per module, per repo convention).
    """

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...


class RetrievalResult(BaseModel):
    """Prefilter output: plain candidate dicts + the pre-limit match count.

    Each candidate is the S5 shape — ``{"sku", "name", "specs", ...}`` —
    ``price``/``in_stock`` may be absent or stale here; :func:`run_turn`
    overwrites them from the facts tool before ranking.
    """

    candidates: list[dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0


class CandidateRetriever(Protocol):
    """The S4 hard-filter half by injection.

    Production adapts ``src.tools.catalog_search`` (ORM rows → candidate dicts);
    tests return canned dicts. ``slots`` excludes the budget slot — budget goes
    through ``budget_max`` so the tool applies its 5% headroom rule.
    """

    def __call__(
        self,
        *,
        category_key: str,
        budget_max: int | None,
        slots: dict[str, Any],
        limit: int,
    ) -> RetrievalResult: ...


class FactsToolLike(Protocol):
    """Structural type for ``src.tools.price_promo_stock.PricePromoStockTool``."""

    async def get_facts_many(self, skus: list[str]) -> dict[str, ProductFacts | None]: ...


class TurnResult(BaseModel):
    """Everything one advisory turn produced, for the caller to render/persist.

    ``profile`` is the same (mutated) object passed in, carried here so the
    endpoint's save step can't forget it. ``facts``/``fetched_at`` are exactly
    what S7 checked against — kept for the audit log (Tầng 5), not re-derived.
    """

    kind: Literal["ask_category", "ask", "recommend", "no_results", "out_of_scope", "unsupported"]
    message: str
    intent: str
    profile: NeedProfile
    quick_replies: list[str] = Field(default_factory=list)
    policy: PolicyDecision | None = None
    total_candidates: int | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    ranking: RankingResult | None = None
    advice: GeneratedAdvice | None = None
    verification: VerificationResult | None = None
    facts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fetched_at: dict[str, str] = Field(default_factory=dict)
    verifier_flags: list[VerifierFlag] = Field(default_factory=list)
    source_panel: list[SourceEntry] = Field(default_factory=list)
    regenerated: bool = False
    used_fallback_table: bool = False
    timings_ms: dict[str, float] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Slot merge & candidate/facts assembly                                       #
# --------------------------------------------------------------------------- #
def _merge_extraction(profile: NeedProfile, s2: S2Result) -> None:
    """Fold an S2 result into the profile: category change first (so slots of
    the old category reset before new ones land), then non-empty slots. ``None``
    and ``[]`` extraction values mean "not mentioned this turn" — merging them
    would pollute the profile with known-but-empty keys.
    """
    if s2.category is not None:
        profile.change_category(s2.category)
    new_slots = {k: v for k, v in s2.slots_moi.items() if v is not None and v != []}
    profile.merge_slots(new_slots)


def _split_budget(profile: NeedProfile) -> tuple[int | None, dict[str, Any]]:
    """Split profile slots into (budget_max, other filterable slots)."""
    raw = profile.slots.get(BUDGET_SLOT_NAME)
    budget = int(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else None
    slots = {
        k: v for k, v in profile.slots.items() if k != BUDGET_SLOT_NAME and v is not None
    }
    return budget, slots


def _apply_facts(
    candidates: list[dict[str, Any]],
    facts_by_sku: dict[str, ProductFacts | None],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    """Overwrite volatile fields from the facts tool and build S7's inputs.

    Returns ``(enriched_candidates, s7_facts, fetched_at)`` where ``s7_facts``
    is the flat per-SKU ``{field: value}`` dict S7 checks claims against
    (specs + ``price``) and ``fetched_at`` maps SKU → snapshot timestamp for
    the freshness check. A SKU unknown to the facts tool gets ``price=None``
    and no timestamp — absence stays absence.
    """
    enriched: list[dict[str, Any]] = []
    s7_facts: dict[str, dict[str, Any]] = {}
    fetched_at: dict[str, str] = {}

    for cand in candidates:
        sku = str(cand.get("sku"))
        product_facts = facts_by_sku.get(sku)
        price = product_facts.sale_price.value if product_facts is not None else None
        in_stock = product_facts.stock.value if product_facts is not None else None
        if product_facts is not None:
            fetched_at[sku] = product_facts.sale_price.fetched_at

        enriched.append({**cand, "price": price, "in_stock": in_stock})
        s7_facts[sku] = {**(cand.get("specs") or {}), "price": price}

    return enriched, s7_facts, fetched_at


# --------------------------------------------------------------------------- #
# Deterministic response builders (no LLM)                                    #
# --------------------------------------------------------------------------- #
def _category_quick_replies() -> list[str]:
    return [load_slot_profile(key).category_label for key in available_categories()]


def _build_question(decision: PolicyDecision) -> tuple[str, list[str]]:
    """One message from the selected slots' hand-authored ``sample_question``s
    ("mỗi lượt ≤3 câu gom 1 tin nhắn"). Quick replies come from the first asked
    slot that has enum ``values`` — one tap answers the primary question.
    """
    message = " ".join(slot.sample_question for slot in decision.slots_to_ask)
    quick_replies: list[str] = []
    for slot in decision.slots_to_ask:
        if slot.values:
            quick_replies = list(slot.values)
            break
    return message, quick_replies


def _assumption_note(profile: NeedProfile, decision: PolicyDecision) -> str:
    """The "đề xuất kèm giả định nêu rõ" suffix for a proceed-with-assumptions
    turn — only the assumptions this decision just recorded, not the whole
    conversation's accumulated list.
    """
    if not decision.proceeded_with_assumptions:
        return ""
    added = profile.assumptions[-len(decision.proceeded_with_assumptions) :]
    return "\n\nLưu ý: " + " ".join(added)


def _corrective_note(verification: VerificationResult) -> str:
    """Specific error feedback for the single S6 regenerate (guardrail §4.6:
    "sinh lại 1 lần với nhắc lỗi cụ thể") — one line per offending claim."""
    lines: list[str] = []
    for claim in verification.claims:
        subject = claim.marker or claim.sku or "?"
        if claim.verdict == "mismatch":
            lines.append(
                f"- {subject}: {claim.field} đúng là {claim.actual_value}, "
                f"không phải {claim.claimed_value}."
            )
        elif claim.honesty_violation:
            lines.append(
                f"- {subject}: KHÔNG có dữ liệu {claim.field} — không được nêu số cụ thể."
            )
    return "\n".join(lines)


class _Stopwatch:
    """Per-stage lap timer feeding ``TurnResult.timings_ms`` (SLA §6.9 + audit)."""

    def __init__(self) -> None:
        self._last = time.perf_counter()
        self.timings: dict[str, float] = {}

    def lap(self, stage: str) -> None:
        now = time.perf_counter()
        self.timings[stage] = round((now - self._last) * 1000, 2)
        self._last = now


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #
async def run_turn(
    text: str,
    profile: NeedProfile,
    *,
    router: LLMRouterLike,
    retriever: CandidateRetriever,
    facts_tool: FactsToolLike,
    retrieve_limit: int = DEFAULT_RETRIEVE_LIMIT,
) -> TurnResult:
    """Run one advisory turn over ``text`` against the session's ``profile``.

    Mutates ``profile`` (slot merge, asked-slot/clarify bookkeeping, category
    change, assumptions) and returns it on the result for the caller to
    persist. Raises whatever the stages raise (``S2ExtractionError``,
    ``S6GenerationError``, ``LLMRouterError``) — retry/fallback policy belongs
    to the caller, not here, same as every stage module.
    """
    sw = _Stopwatch()
    s1 = run_s1(text)
    sw.lap("s1")
    s2 = await extract(router, text, s1, profile)
    sw.lap("s2")
    _merge_extraction(profile, s2)

    if s2.intent == "ngoai_pham_vi":
        return TurnResult(
            kind="out_of_scope",
            message=_OUT_OF_SCOPE_MESSAGE,
            intent=s2.intent,
            profile=profile,
            timings_ms=sw.timings,
        )
    if s2.intent != "tu_van":
        return TurnResult(
            kind="unsupported",
            message=_UNSUPPORTED_MESSAGE,
            intent=s2.intent,
            profile=profile,
            timings_ms=sw.timings,
        )

    if profile.category is None:
        return TurnResult(
            kind="ask_category",
            message=_ASK_CATEGORY_MESSAGE,
            intent=s2.intent,
            profile=profile,
            quick_replies=_category_quick_replies(),
            timings_ms=sw.timings,
        )

    # S4 prefilter BEFORE S3: candidate_count comes from the real filtered
    # catalog, and the candidates ride along for timely feedback on ask turns.
    budget_max, filter_slots = _split_budget(profile)
    retrieval = retriever(
        category_key=profile.category,
        budget_max=budget_max,
        slots=filter_slots,
        limit=retrieve_limit,
    )
    sw.lap("s4_prefilter")

    decision = decide_policy(profile, retrieval.total_count)
    sw.lap("s3_policy")

    if decision.action == "ask":
        message, quick_replies = _build_question(decision)
        return TurnResult(
            kind="ask",
            message=message,
            intent=s2.intent,
            profile=profile,
            quick_replies=quick_replies,
            policy=decision,
            total_candidates=retrieval.total_count,
            candidates=retrieval.candidates,
            timings_ms=sw.timings,
        )

    if not retrieval.candidates:
        return TurnResult(
            kind="no_results",
            message=_NO_RESULTS_MESSAGE,
            intent=s2.intent,
            profile=profile,
            policy=decision,
            total_candidates=retrieval.total_count,
            timings_ms=sw.timings,
        )

    # Proceed: facts (source of truth for volatile fields) → S5 → S6 → S7/S8.
    skus = [str(c.get("sku")) for c in retrieval.candidates]
    facts_by_sku = await facts_tool.get_facts_many(skus)
    candidates, s7_facts, fetched_at = _apply_facts(retrieval.candidates, facts_by_sku)
    sw.lap("s4_facts")

    slot_profile = load_slot_profile(profile.category)
    ranking = rank_candidates(candidates, profile, slot_profile)
    sw.lap("s5_rank")

    advice = await generate(router, ranking, candidates, profile)
    sw.lap("s6_generate")
    verification = verify(advice.text, advice.marker_map, s7_facts, fetched_at=fetched_at)
    enforcement = enforce(advice.text, verification)

    # Escalation ladder (guardrail §4.6): regenerate once with specific error
    # feedback; a still-bad retry degrades to the never-fabricates table.
    regenerated = False
    used_fallback = False
    if enforcement.incident_count > MAX_INCIDENTS:
        regenerated = True
        advice = await generate(
            router, ranking, candidates, profile,
            corrective_note=_corrective_note(verification),
        )
        sw.lap("s6_regenerate")
        verification = verify(advice.text, advice.marker_map, s7_facts, fetched_at=fetched_at)
        enforcement = enforce(advice.text, verification)
        used_fallback = enforcement.incident_count > MAX_INCIDENTS

    text_out = render_fallback_table(ranking, candidates) if used_fallback else enforcement.text
    sw.lap("s7_verify")

    message = text_out + _assumption_note(profile, decision)
    return TurnResult(
        kind="recommend",
        message=message,
        intent=s2.intent,
        profile=profile,
        policy=decision,
        total_candidates=retrieval.total_count,
        candidates=candidates,
        ranking=ranking,
        advice=advice,
        verification=verification,
        facts=s7_facts,
        fetched_at=fetched_at,
        verifier_flags=enforcement.flags,
        source_panel=build_source_panel(s7_facts, facts_by_sku),
        regenerated=regenerated,
        used_fallback_table=used_fallback,
        timings_ms=sw.timings,
    )
