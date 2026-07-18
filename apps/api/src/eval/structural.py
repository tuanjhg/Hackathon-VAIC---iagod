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
    )


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
    }
