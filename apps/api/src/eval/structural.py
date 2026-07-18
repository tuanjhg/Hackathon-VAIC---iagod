"""Tier 1 — structural coverage metrics over replayed golden conversations.

Deterministic, no LLM judge. Answers "how much of the golden set can the current
bot even engage": which product category each conversation is really about, which
of those the bot supports (has a slot profile for), what the bot actually did per
turn, and where it stayed on-scope vs refused/degraded.

Category support is read live from :func:`available_categories`, so adding a slot
profile automatically widens what counts as "supported" here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import ceil
from typing import Any

from src.eval.replay import ReplayedConversation
from src.pipeline.slots import available_categories

# Keyword → catalog category_key for detecting what a golden conversation is
# *about* (from its user turns). Order matters: more specific phrases first.
# ``None`` marks product families the real catalog does not carry at all.
_GOLDEN_CATEGORY_KEYWORDS: list[tuple[str, str | None]] = [
    ("máy rửa chén", "may_rua_chen"),
    ("rửa chén", "may_rua_chen"),
    ("máy giặt", "may_giat"),
    ("máy sấy", "may_say"),
    ("tủ đông", "tu_mat_dong"),
    ("tủ mát", "tu_mat_dong"),
    ("tủ lạnh", "tu_lanh"),
    ("máy lạnh", "may_lanh"),
    ("điều hòa", "may_lanh"),
    ("nước nóng", "may_nuoc_nong"),
    ("bình nóng", "may_nuoc_nong"),
    ("màn hình", "man_hinh"),
    ("máy tính để bàn", "pc_de_ban"),
    ("máy tính bảng", "may_tinh_bang"),
    ("máy in", "may_in"),
    ("đồng hồ thông minh", "dong_ho_tm"),
    ("micro thu âm", "micro_thu_am"),
    ("micro karaoke", "micro_karaoke"),
    ("micro", "micro_karaoke"),
    # families with no catalog coverage
    ("laptop", None),
    ("tivi", None),
    ("smart tv", None),
    ("tai nghe", None),
    ("loa", None),
    ("quạt", None),
]


def detect_golden_category(conversation_user_text: str) -> str | list[str] | None:
    """Best-effort intended product category(ies) from the golden user turns.

    Returns a single key, a list when several are mentioned, or ``None`` when no
    product family is detected (order-lookup / policy-only conversations).
    """
    text = conversation_user_text.lower()
    found: list[str | None] = []
    for keyword, category in _GOLDEN_CATEGORY_KEYWORDS:
        if keyword == "micro" and any(
            existing in {"micro_karaoke", "micro_thu_am"} for existing in found
        ):
            continue
        if keyword in text and category not in found:
            found.append(category)
    real = [c for c in found if c is not None]
    if real:
        return real[0] if len(real) == 1 else real
    if found:  # only out-of-catalog families matched
        return "__not_in_catalog__"
    return None


@dataclass
class ConversationReport:
    id: str
    source: str
    golden_category: str | list[str] | None
    engaged_category: str | None
    supported: bool
    recommended: bool
    turn_kinds: dict[str, int] = field(default_factory=dict)
    error_turns: int = 0
    degraded_turns: int = 0
    degraded_stages: dict[str, int] = field(default_factory=dict)
    stage_latency_ms: dict[str, list[float]] = field(default_factory=dict)
    kind_latency_ms: dict[str, list[float]] = field(default_factory=dict)
    post_guardrail_claims: int = 0
    post_guardrail_mismatches: int = 0
    post_guardrail_unverifiable: int = 0
    post_guardrail_honesty_violations: int = 0
    honesty_opportunities: int = 0
    corrected_claims: int = 0
    omitted_claims: int = 0
    policy_grounding_failures: int = 0


def classify_conversation(replayed: ReplayedConversation) -> ConversationReport:
    supported_categories = set(available_categories())
    convo = replayed.conversation
    golden_cat = detect_golden_category(" ".join(convo.user_turns))
    engaged = replayed.category
    kinds = Counter(t.kind for t in replayed.turns)
    degraded = Counter(
        stage
        for turn in replayed.turns
        if turn.result is not None
        for stage in turn.result.degraded_stages
    )
    stage_latency: dict[str, list[float]] = {}
    kind_latency: dict[str, list[float]] = {}
    post_claims = 0
    post_mismatches = 0
    post_unverifiable = 0
    post_honesty = 0
    honesty_opportunities = 0
    corrected = 0
    omitted = 0
    policy_grounding_failures = 0
    for turn in replayed.turns:
        result = turn.result
        if result is None:
            continue
        total_latency = round(sum(result.timings_ms.values()), 2)
        kind_latency.setdefault(result.kind, []).append(total_latency)
        for stage, latency in result.timings_ms.items():
            stage_latency.setdefault(stage, []).append(latency)
        final = result.output_verification
        if final is not None:
            post_claims += len(final.claims)
            post_mismatches += sum(claim.verdict == "mismatch" for claim in final.claims)
            post_unverifiable += sum(claim.verdict == "unverifiable" for claim in final.claims)
            post_honesty += len(final.honesty_violations)
        if result.verification is not None:
            honesty_opportunities += len(result.verification.honesty_violations)
        corrected += sum(flag.action == "corrected" for flag in result.verifier_flags)
        omitted += sum(flag.action == "removed" for flag in result.verifier_flags)
        policy_grounding_failures += result.policy_grounding_passed is False

    return ConversationReport(
        id=convo.id,
        source=convo.source,
        golden_category=golden_cat,
        engaged_category=engaged,
        supported=engaged in supported_categories if engaged else False,
        recommended=replayed.recommended,
        turn_kinds=dict(kinds),
        error_turns=kinds.get("error", 0),
        degraded_turns=sum(
            1 for turn in replayed.turns
            if turn.result is not None and turn.result.degraded_stages
        ),
        degraded_stages=dict(degraded),
        stage_latency_ms=stage_latency,
        kind_latency_ms=kind_latency,
        post_guardrail_claims=post_claims,
        post_guardrail_mismatches=post_mismatches,
        post_guardrail_unverifiable=post_unverifiable,
        post_guardrail_honesty_violations=post_honesty,
        honesty_opportunities=honesty_opportunities,
        corrected_claims=corrected,
        omitted_claims=omitted,
        policy_grounding_failures=policy_grounding_failures,
    )


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def _latency_summary(values: list[float], threshold_ms: float) -> dict[str, Any]:
    p50 = _percentile(values, 0.50)
    p95 = _percentile(values, 0.95)
    return {
        "samples": len(values),
        "p50_ms": p50,
        "p95_ms": p95,
        "threshold_ms": threshold_ms,
        "pass_pct": round(100 * sum(value <= threshold_ms for value in values) / len(values), 1)
        if values
        else None,
        "passes": p95 <= threshold_ms if p95 is not None else None,
    }


def aggregate(reports: list[ConversationReport]) -> dict[str, Any]:
    total = len(reports)
    if total == 0:
        return {"total": 0}

    turn_kinds: Counter[str] = Counter()
    for report in reports:
        turn_kinds.update(report.turn_kinds)

    recommended = sum(1 for r in reports if r.recommended)
    supported_engaged = sum(1 for r in reports if r.supported)
    any_error = sum(1 for r in reports if r.error_turns > 0)
    any_degraded = sum(1 for r in reports if r.degraded_turns > 0)
    degraded_stages: Counter[str] = Counter()
    for report in reports:
        degraded_stages.update(report.degraded_stages)
    handoff = sum(1 for r in reports if r.turn_kinds.get("handoff", 0) > 0)
    policy_answered = sum(1 for r in reports if r.turn_kinds.get("policy", 0) > 0)
    stage_latency: dict[str, list[float]] = {}
    kind_latency: dict[str, list[float]] = {}
    for report in reports:
        for stage, values in report.stage_latency_ms.items():
            stage_latency.setdefault(stage, []).extend(values)
        for kind, values in report.kind_latency_ms.items():
            kind_latency.setdefault(kind, []).extend(values)
    clarification_latency = [
        *kind_latency.get("ask_category", []),
        *kind_latency.get("ask", []),
    ]
    recommendation_latency = kind_latency.get("recommend", [])
    post_claims = sum(report.post_guardrail_claims for report in reports)
    post_mismatches = sum(report.post_guardrail_mismatches for report in reports)
    post_unverifiable = sum(report.post_guardrail_unverifiable for report in reports)
    post_honesty = sum(report.post_guardrail_honesty_violations for report in reports)
    policy_grounding_failures = sum(report.policy_grounding_failures for report in reports)
    honesty_opportunities = sum(report.honesty_opportunities for report in reports)
    escaped = post_mismatches + post_honesty + policy_grounding_failures
    honesty_recall = (
        round(100 * max(0, honesty_opportunities - post_honesty) / honesty_opportunities, 1)
        if honesty_opportunities
        else None
    )
    s2_sla = _latency_summary(stage_latency.get("s2", []), 700.0)
    clarification_sla = _latency_summary(clarification_latency, 3000.0)
    recommendation_sla = _latency_summary(recommendation_latency, 5000.0)
    guardrail_sla = {
        "post_guardrail_claims": post_claims,
        "escaped_mismatches": post_mismatches,
        "escaped_honesty_violations": post_honesty,
        "policy_grounding_failures": policy_grounding_failures,
        "unverifiable_claims": post_unverifiable,
        "hallucination_rate_pct": round(100 * escaped / post_claims, 2) if post_claims else 0.0,
        "honesty_opportunities": honesty_opportunities,
        "honesty_recall_pct": honesty_recall,
        "corrected_claims": sum(report.corrected_claims for report in reports),
        "omitted_claims": sum(report.omitted_claims for report in reports),
        "passes_zero_hallucination": escaped == 0,
        "passes_honesty_recall": honesty_recall >= 95.0 if honesty_recall is not None else None,
    }
    evaluated_passes = [
        value
        for value in (
            s2_sla["passes"],
            clarification_sla["passes"],
            recommendation_sla["passes"],
            guardrail_sla["passes_zero_hallucination"],
            guardrail_sla["passes_honesty_recall"],
        )
        if value is not None
    ]

    # Golden intended-category buckets: in-catalog+supported / in-catalog-only /
    # not-in-catalog / non-product.
    supported_categories = set(available_categories())
    buckets: Counter[str] = Counter()
    for report in reports:
        gc = report.golden_category
        cats = gc if isinstance(gc, list) else [gc]
        primary = cats[0] if cats else None
        if primary is None:
            buckets["non_product"] += 1
        elif primary == "__not_in_catalog__":
            buckets["not_in_catalog"] += 1
        elif primary in supported_categories:
            buckets["in_catalog_supported"] += 1
        else:
            buckets["in_catalog_no_profile"] += 1

    return {
        "total": total,
        "by_source": dict(Counter(r.source for r in reports)),
        "recommended_convs": recommended,
        "recommended_pct": round(100 * recommended / total, 1),
        "engaged_supported_category_convs": supported_engaged,
        "convs_with_error_turn": any_error,
        "error_free_pct": round(100 * (total - any_error) / total, 1),
        "degraded_convs": any_degraded,
        "degraded_stage_distribution": dict(degraded_stages.most_common()),
        "handoff_convs": handoff,
        "policy_answered_convs": policy_answered,
        "turn_kind_distribution": dict(turn_kinds.most_common()),
        "golden_intent_buckets": dict(buckets),
        "supported_categories": sorted(supported_categories),
        "sla": {
            "s2": s2_sla,
            "clarification": clarification_sla,
            "recommendation": recommendation_sla,
            "guardrail": guardrail_sla,
            "overall_passes": all(evaluated_passes),
        },
    }
