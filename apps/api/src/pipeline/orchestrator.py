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

* Only the ``tu_van`` intent gets the full pipeline. Other intents route to a
  grounded policy answer, a safe transaction handoff, or an explicit scope
  boundary instead of silently pretending the requested capability exists.
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

import asyncio
import re
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from src.pipeline.humanize import fold_ascii
from src.pipeline.need_profile import NeedProfile
from src.pipeline.policy_answer import PolicySource, generate_policy_answer
from src.pipeline.preprocess import run_s1
from src.pipeline.s2_extract import S2ExtractionError, S2Result, deterministic_fallback, extract
from src.pipeline.s3_policy import PolicyDecision, decide_policy
from src.pipeline.s5_ranking import BUDGET_SLOT_NAME, RankingResult, rank_candidates
from src.pipeline.s6_generate import GeneratedAdvice, S6GenerationError, generate
from src.pipeline.s8_respond import (
    MAX_INCIDENTS,
    SourceEntry,
    VerifierFlag,
    build_source_panel,
    enforce,
    render_fallback_table,
)
from src.pipeline.slots import available_categories, load_slot_profile
from src.rag.models import SearchResult
from src.router.client import LLMRouterError
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

S2_DEADLINE_SECONDS = 0.65
"""Hard S2 budget: keeps the documented 700 ms p95 stage SLA."""

S6_DEADLINE_SECONDS = 3.5
"""Generation budget within the 5 s end-to-end recommendation SLA."""

RECOMMEND_DEADLINE_SECONDS = 4.8
"""Total soft ceiling used to leave time for deterministic S4/S5/S7 work."""

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
_TRANSACTION_HANDOFF_MESSAGE = (
    "Dạ hiện em chưa xem hoặc thay đổi được đơn hàng, số lượng còn tại cửa hàng và "
    "lịch giao đang cập nhật nên không thể xác nhận các thông tin này ạ. Anh/chị vui "
    "lòng mở mục Đơn hàng trên website hoặc ứng dụng, hoặc liên hệ bộ phận chăm sóc "
    "khách hàng. Em vẫn có thể tiếp tục tư vấn chọn sản phẩm phù hợp cho anh/chị."
)

_UNSUPPORTED_MESSAGES: dict[str, str] = {
    "so_sanh_truc_tiep": (
        "Dạ hiện em chưa thể đối chiếu chính xác các mẫu chỉ từ tên trong hội thoại ạ. "
        "Anh/chị có thể mở trang từng sản phẩm và dùng tính năng So sánh, hoặc cho em "
        "biết nhu cầu chính để em đề xuất tối đa 3 lựa chọn có dữ liệu kiểm chứng."
    ),
    "hoi_chi_tiet_sp": (
        "Dạ em chưa xác định chắc chắn sản phẩm cụ thể anh/chị đang nhắc tới nên không "
        "muốn đoán thông số ạ. Anh/chị vui lòng mở trang chi tiết sản phẩm, hoặc cho em "
        "biết ngành hàng và nhu cầu để em tư vấn từ dữ liệu hiện có."
    ),
    "policy_faq": (
        "Dạ nguồn chính sách hiện chưa sẵn sàng nên em chưa thể trả lời chính xác câu "
        "này ạ. Anh/chị vui lòng xem trang chính sách chính thức hoặc liên hệ chăm sóc "
        "khách hàng."
    ),
}

_PROFILE_VALUE_LABELS: dict[str, str] = {
    "phong_ngu": "phòng ngủ",
    "phong_khach": "phòng khách",
    "van_phong": "văn phòng",
    "tiet_kiem_dien": "tiết kiệm điện",
    "em": "chạy êm",
    "ben": "bền bỉ",
    "gia_re": "giá dễ chịu",
}

_SOCIAL_QUICK_REPLIES = [
    "Tư vấn máy lạnh",
    "Tư vấn tủ lạnh",
    "Xem chính sách trả góp",
]


def _basic_social_reply(text: str, *, has_category: bool) -> str | None:
    """Answer short social turns before S2; product-bearing turns continue normally."""
    if has_category:
        return None
    folded = fold_ascii(text).replace("_", " ")
    tokens = re.findall(r"[a-z0-9]+", folded)
    if not tokens or len(tokens) > 10:
        return None
    clean = " ".join(tokens)
    token_set = set(tokens)
    if (
        token_set.intersection({"hi", "hello", "alo"})
        or tokens[0] == "chao"
        or clean.startswith("xin chao")
        or clean in {"khoe khong", "em khoe khong", "ban khoe khong"}
    ):
        return (
            "Dạ em chào anh/chị ạ! Em có thể tư vấn chọn sản phẩm, so sánh theo nhu cầu "
            "và giải đáp chính sách từ nguồn hiện có. Anh/chị đang quan tâm sản phẩm nào ạ?"
        )
    if "cam on" in clean or token_set.intersection({"thanks", "thank"}):
        return (
            "Dạ em rất vui được hỗ trợ anh/chị ạ. Khi cần chọn sản phẩm hoặc hỏi chính sách, "
            "anh/chị cứ nhắn nhu cầu cho em nhé."
        )
    if token_set.intersection({"bye", "goodbye"}) or clean.startswith("tam biet"):
        return "Dạ em chào anh/chị ạ. Khi cần tư vấn điện máy, anh/chị quay lại nhắn em nhé!"
    if any(
        phrase in clean
        for phrase in ("lam duoc gi", "ho tro gi", "giup duoc gi", "co the lam gi")
    ):
        return (
            "Dạ em có thể giúp anh/chị chọn sản phẩm theo ngân sách và nhu cầu, so sánh các "
            "lựa chọn có dữ liệu, và trả lời chính sách từ tài liệu hiện có ạ."
        )
    return None


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


class PolicySearchLike(Protocol):
    """The policy RAG retriever by injection (``src.rag.pipeline.PolicyIndexPipeline``)."""

    def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...


class TurnResult(BaseModel):
    """Everything one advisory turn produced, for the caller to render/persist.

    ``profile`` is the same (mutated) object passed in, carried here so the
    endpoint's save step can't forget it. ``facts``/``fetched_at`` are exactly
    what S7 checked against — kept for the audit log (Tầng 5), not re-derived.
    """

    kind: Literal[
        "ask_category", "ask", "recommend", "no_results", "handoff", "out_of_scope",
        "unsupported", "policy", "small_talk"
    ]
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
    output_verification: VerificationResult | None = None
    policy_grounding_passed: bool | None = None
    facts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fetched_at: dict[str, str] = Field(default_factory=dict)
    verifier_flags: list[VerifierFlag] = Field(default_factory=list)
    source_panel: list[SourceEntry] = Field(default_factory=list)
    regenerated: bool = False
    used_fallback_table: bool = False
    degraded_stages: list[str] = Field(default_factory=list)
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


def _policy_source_panel(sources: list[PolicySource]) -> list[SourceEntry]:
    """Cite the policy documents/sections an answer was grounded in, reusing the
    same "Nguồn dữ liệu" panel the recommendation path fills."""
    return [
        SourceEntry(
            sku=Path(source.source_path).stem,
            field=source.heading or "(toàn văn)",
            dataset="policy",
        )
        for source in sources
    ]


def _build_question(decision: PolicyDecision) -> tuple[str, list[str]]:
    """One message from the selected slots' hand-authored ``sample_question``s
    ("mỗi lượt ≤3 câu gom 1 tin nhắn"). Quick replies come from the first asked
    slot that has enum ``values`` — one tap answers the primary question.
    """
    questions = " ".join(slot.sample_question for slot in decision.slots_to_ask)
    message = "Dạ " + questions
    if decision.question_reason:
        message += " Em hỏi vì các thông tin này giúp thu hẹp lựa chọn và tránh gợi ý sai ạ."
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


def _needs_summary(profile: NeedProfile) -> str:
    """Short deterministic need recap without turning profile numbers into claims."""
    assert profile.category is not None
    category = load_slot_profile(profile.category).category_label.lower()
    details: list[str] = []
    room = profile.slots.get("loai_phong")
    if isinstance(room, str) and room in _PROFILE_VALUE_LABELS:
        details.append(f"dùng cho {_PROFILE_VALUE_LABELS[room]}")
    priorities = profile.slots.get("uu_tien")
    values = priorities if isinstance(priorities, list) else [priorities]
    priority_labels = [
        _PROFILE_VALUE_LABELS[str(value)]
        for value in values
        if value is not None and str(value) in _PROFILE_VALUE_LABELS
    ]
    if priority_labels:
        details.append("ưu tiên " + " và ".join(priority_labels))
    if "ngan_sach_max" in profile.slots:
        details.append("trong ngân sách đã nêu")
    if "dien_tich_m2" in profile.slots:
        details.append("phù hợp không gian đã cung cấp")
    if "so_nguoi_dung" in profile.slots:
        details.append("theo quy mô gia đình đã chia sẻ")
    suffix = ", ".join(details) if details else "theo nhu cầu đã chia sẻ"
    return f"Dạ em đã ghi nhận anh/chị cần {category}, {suffix}."


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


def _marker_map(ranking: RankingResult) -> dict[str, str]:
    return {f"[{index}]": item.sku for index, item in enumerate(ranking.top, start=1)}


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
    policy_search: PolicySearchLike | None = None,
    retrieve_limit: int = DEFAULT_RETRIEVE_LIMIT,
) -> TurnResult:
    """Run one advisory turn over ``text`` against the session's ``profile``.

    Mutates ``profile`` (slot merge, asked-slot/clarify bookkeeping, category
    change, assumptions) and returns it on the result for the caller to
    persist. Provider/extraction failures at S2 and S6 degrade to deterministic
    output and are recorded in ``degraded_stages``; catalog/facts/programming
    errors still surface instead of being silently hidden.
    """
    sw = _Stopwatch()
    turn_started = time.perf_counter()
    degraded_stages: list[str] = []
    s1 = run_s1(text)
    sw.lap("s1")
    social_reply = _basic_social_reply(text, has_category=s1.category_hint is not None)
    if social_reply is not None:
        return TurnResult(
            kind="small_talk",
            message=social_reply,
            intent="giao_tiep_co_ban",
            profile=profile,
            quick_replies=_SOCIAL_QUICK_REPLIES,
            timings_ms=sw.timings,
        )
    deterministic_s2 = deterministic_fallback(text, s1, profile)
    try:
        s2 = await asyncio.wait_for(
            extract(router, text, s1, profile), timeout=S2_DEADLINE_SECONDS
        )
    except (TimeoutError, LLMRouterError, S2ExtractionError):
        s2 = deterministic_s2
        degraded_stages.append("s2")
    sw.lap("s2")
    _merge_extraction(profile, s2)

    if s2.intent == "ngoai_pham_vi":
        return TurnResult(
            kind="out_of_scope",
            message=_OUT_OF_SCOPE_MESSAGE,
            intent=s2.intent,
            profile=profile,
            degraded_stages=degraded_stages,
            timings_ms=sw.timings,
        )
    if s2.intent == "ho_tro_giao_dich":
        return TurnResult(
            kind="handoff",
            message=_TRANSACTION_HANDOFF_MESSAGE,
            intent=s2.intent,
            profile=profile,
            quick_replies=["Tiếp tục tư vấn sản phẩm", "Xem chính sách giao hàng"],
            degraded_stages=degraded_stages,
            timings_ms=sw.timings,
        )
    if s2.intent == "policy_faq" and policy_search is not None:
        results = policy_search.search(text, limit=5)
        try:
            answer = await asyncio.wait_for(
                generate_policy_answer(router, text, results), timeout=S6_DEADLINE_SECONDS
            )
        except (TimeoutError, LLMRouterError):
            degraded_stages.append("policy_faq")
            answer = None
        sw.lap("policy_faq")
        return TurnResult(
            kind="policy",
            message=answer.text if answer is not None else _UNSUPPORTED_MESSAGES["policy_faq"],
            intent=s2.intent,
            profile=profile,
            source_panel=_policy_source_panel(answer.sources) if answer is not None else [],
            # Both paths are safe: validated/extractive when an answer exists,
            # otherwise the fixed honest-unavailable message below.
            policy_grounding_passed=True,
            used_fallback_table=answer.fallback_used if answer is not None else False,
            degraded_stages=degraded_stages,
            timings_ms=sw.timings,
        )
    if s2.intent != "tu_van":
        return TurnResult(
            kind="unsupported",
            message=_UNSUPPORTED_MESSAGES.get(
                s2.intent,
                "Dạ chức năng này hiện chưa được hỗ trợ nên em không muốn trả lời thiếu căn cứ ạ.",
            ),
            intent=s2.intent,
            profile=profile,
            degraded_stages=degraded_stages,
            timings_ms=sw.timings,
        )

    if profile.category is None:
        return TurnResult(
            kind="ask_category",
            message=_ASK_CATEGORY_MESSAGE,
            intent=s2.intent,
            profile=profile,
            quick_replies=_category_quick_replies(),
            degraded_stages=degraded_stages,
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
            degraded_stages=degraded_stages,
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
            degraded_stages=degraded_stages,
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

    remaining = max(
        0.05,
        RECOMMEND_DEADLINE_SECONDS - (time.perf_counter() - turn_started),
    )
    try:
        advice = await asyncio.wait_for(
            generate(router, ranking, candidates, profile),
            timeout=min(S6_DEADLINE_SECONDS, remaining),
        )
    except (TimeoutError, LLMRouterError, S6GenerationError):
        degraded_stages.append("s6")
        sw.lap("s6_generate")
        message = (
            _needs_summary(profile)
            + "\n\n"
            + render_fallback_table(ranking, candidates)
            + _assumption_note(profile, decision)
        )
        output_verification = verify(
            message, _marker_map(ranking), s7_facts, fetched_at=fetched_at
        )
        return TurnResult(
            kind="recommend",
            message=message,
            intent=s2.intent,
            profile=profile,
            policy=decision,
            total_candidates=retrieval.total_count,
            candidates=candidates,
            ranking=ranking,
            facts=s7_facts,
            fetched_at=fetched_at,
            source_panel=build_source_panel(s7_facts, facts_by_sku),
            output_verification=output_verification,
            used_fallback_table=True,
            degraded_stages=degraded_stages,
            timings_ms=sw.timings,
        )
    sw.lap("s6_generate")
    verification = verify(advice.text, advice.marker_map, s7_facts, fetched_at=fetched_at)
    enforcement = enforce(advice.text, verification)

    # Escalation ladder (guardrail §4.6): regenerate once with specific error
    # feedback; a still-bad retry degrades to the never-fabricates table.
    regenerated = False
    used_fallback = False
    if enforcement.incident_count > MAX_INCIDENTS:
        regenerated = True
        remaining = max(
            0.05,
            RECOMMEND_DEADLINE_SECONDS - (time.perf_counter() - turn_started),
        )
        try:
            advice = await asyncio.wait_for(
                generate(
                    router, ranking, candidates, profile,
                    corrective_note=_corrective_note(verification),
                ),
                timeout=remaining,
            )
        except (TimeoutError, LLMRouterError, S6GenerationError):
            degraded_stages.append("s6_regenerate")
            used_fallback = True
            sw.lap("s6_regenerate")
        else:
            sw.lap("s6_regenerate")
            verification = verify(advice.text, advice.marker_map, s7_facts, fetched_at=fetched_at)
            enforcement = enforce(advice.text, verification)
            used_fallback = enforcement.incident_count > MAX_INCIDENTS

    text_out = render_fallback_table(ranking, candidates) if used_fallback else enforcement.text
    sw.lap("s7_verify")

    message = _needs_summary(profile) + "\n\n" + text_out + _assumption_note(profile, decision)
    output_verification = verify(
        message,
        advice.marker_map if not used_fallback else _marker_map(ranking),
        s7_facts,
        fetched_at=fetched_at,
    )
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
        output_verification=output_verification,
        facts=s7_facts,
        fetched_at=fetched_at,
        verifier_flags=enforcement.flags,
        source_panel=build_source_panel(s7_facts, facts_by_sku),
        regenerated=regenerated,
        used_fallback_table=used_fallback,
        degraded_stages=degraded_stages,
        timings_ms=sw.timings,
    )
