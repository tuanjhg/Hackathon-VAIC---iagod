"""S5 — Fit-score ranking (deterministic, pure function).

Implements ADR C4/C5 of ``docs/research/dmx-tech-decisions.md`` and §3 "S5" of
``docs/research/dmx-ai-workflow-v1.md``:

    score(sp) = Σ wᵢ · match(slotᵢ, attrᵢ(sp))     # trọng số theo ưu tiên khách nói
              + bonus_khuyến_mãi + bonus_sẵn_hàng
              − penalty (vượt ngân sách, thiếu field quan trọng...)

This stage takes plain candidate dicts (NOT ORM ``Product`` objects) so it has
zero SQLAlchemy/LLM/I/O dependency and is trivially unit-testable. Each candidate:

    {"sku": str, "name": str, "specs": dict[str, Any], "price": int | None,
     "in_stock": bool | None}

``specs`` is a ``Product.specs_json``-shaped dict of arbitrary per-category keys.

Design choices (the ADR fixes the *shape*, not the exact numbers — these are
documented here and pinned by the tests):

* **Criteria** are exactly the spec fields the priority slot (`uu_tien`) maps to
  via its ``catalog_field`` list — for máy lạnh: ``inverter``,
  ``energy_efficiency``, ``noise_db_indoor``. Everything else is price/stock,
  handled as bonus/penalty per the ADR formula (price is never a `match` term).

* **Weighting from stated priority**: a criterion tied to a priority the
  customer actually stated gets weight ``STATED_PRIORITY_WEIGHT`` (3x); a
  criterion nobody mentioned gets ``UNSTATED_WEIGHT`` (1x). Differences on
  unstated priorities are noise; differences on *stated* ones are the trade-off
  that matters. A priority value maps to its criterion field(s) by name via
  ``_PRIORITY_FIELD_KEYWORDS`` (the may-lanh seed of the value→field mapping the
  Category Profile Compiler, ADR A7, will later generate).

* **match / normalization**: each numeric field is min-max normalized *across
  the candidate set this turn* (relative to what is actually available now, not
  an arbitrary absolute scale), oriented by field semantics inferred from the
  name (``noise``/``price`` → lower-is-better, else higher-is-better). Booleans
  map True→1.0 / False→0.0. A field with no spread across the set contributes a
  neutral 1.0 (constant → does not affect ranking).

* **Missing data is honest, never fatal** (ADR: "field thiếu không phạt về 0 —
  data bẩn không được giết sản phẩm tốt"): a null criterion field is listed in
  ``missing_fields`` and contributes 0 to its `match` term. A null field tied to
  a *stated* priority additionally incurs a small fixed penalty
  (``MISSING_STATED_FIELD_PENALTY``) — surfaced as a ``penalty:missing:*`` entry,
  not silently swallowed.

* **Over budget**: if a budget slot and a price are both present and price
  exceeds it, apply ``OVER_BUDGET_PENALTY`` (deprioritize) — NOT a hard exclude
  (S4/catalog_search already did hard filtering; S5 only nudges overshoots down).

* **Anti-pick heuristic** (this dataset has no ``featured``/reviews field at the
  S5 layer): the lowest-scoring candidate *among those with price data*. A
  priced product is what a shopper can actually click and buy — superficially
  appealing — so the worst-fitting priced one is the honest "don't pick this".
  Falls back to the overall lowest score when nothing is priced.

* **Trade-off extraction** (deterministic, ADR "bổ sung 17/07"): for each pair
  in the top-3, over the *stated-priority* criteria only, find criteria whose
  advantage direction reverses (A better on X, worse on Y). Emit a trade-off
  only when the direction genuinely reverses (both sides win ≥1 criterion) — a
  pure domination is not a trade-off. When the customer stated no priority, the
  pool falls back to the full criterion set so pairs are still comparable.

The full per-candidate breakdown (per-criterion contributions, missing flags) is
kept as raw material for the anti-pick "vì sao không nên chọn" explanation and
for S6 to turn into advisory prose.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from src.pipeline.need_profile import NeedProfile
from src.pipeline.slots import SlotDef, SlotProfile

__all__ = [
    "PRIORITY_SLOT_NAME",
    "BUDGET_SLOT_NAME",
    "ScoreBreakdown",
    "TradeOff",
    "RankingResult",
    "rank_candidates",
]

# --------------------------------------------------------------------------- #
# Tunables (documented above; pinned by tests, not by the ADR).              #
# --------------------------------------------------------------------------- #
PRIORITY_SLOT_NAME = "uu_tien"
"""Real ASCII slot name (no diacritics) for stated priorities in this dataset.
Kept as a named constant rather than a magic string, but resolved against the
slot profile's ``optional_slots`` so a renamed profile is caught, not assumed."""

BUDGET_SLOT_NAME = "ngan_sach_max"
"""Slot holding the customer's max budget (VND), used only for the soft
over-budget penalty — S5 never hard-excludes on it."""

STATED_PRIORITY_WEIGHT = 3.0
UNSTATED_WEIGHT = 1.0
PRICE_PRESENT_BONUS = 0.05
IN_STOCK_BONUS = 0.05
OVER_BUDGET_PENALTY = 0.5
MISSING_STATED_FIELD_PENALTY = 0.5

_SPEC_FIELD_PREFIX = "specs."

# Seed value→criterion-field mapping for máy lạnh. Substring match against the
# priority slot's catalog_field names. The Category Profile Compiler (ADR A7)
# will generate this per category later; hand-authored here as the Phase-0
# fallback, mirroring the slots/*.yaml "bản tay" approach.
_PRIORITY_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tiet_kiem_dien": ("inverter", "energy"),  # energy-saving
    "em": ("noise",),  # quiet
    "ben": ("warranty",),  # durable
    "gia_re": (),  # cheap — handled via budget/price, not a spec `match` term
}

# Breakdown key namespaces (criteria are bare field names; everything with a
# ``:`` is a bonus/penalty and is excluded from trade-off comparison).
_BONUS_PRICE_KEY = "bonus:price_available"
_BONUS_STOCK_KEY = "bonus:in_stock"
_PENALTY_OVER_BUDGET_KEY = "penalty:over_budget"
_PENALTY_MISSING_PREFIX = "penalty:missing:"


class ScoreBreakdown(BaseModel):
    """Full, reconstructable score for one candidate.

    ``sum(per_criterion.values()) == total_score`` always holds — criteria carry
    bare field-name keys, bonuses/penalties carry ``namespace:...`` keys.
    """

    sku: str
    total_score: float
    per_criterion: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    price: int | None = None


class TradeOff(BaseModel):
    """A single decision the customer must make between two top candidates.

    Only criteria tied to *stated* priorities appear (trade-offs on things the
    customer never mentioned are noise). S6 turns these structured facts into
    prose; S5 supplies the raw values, not the wording.
    """

    sku_a: str
    sku_b: str
    a_wins_on: list[str]
    b_wins_on: list[str]
    values: dict[str, tuple[Any, Any]]


class RankingResult(BaseModel):
    top: list[ScoreBreakdown]
    anti_pick: ScoreBreakdown | None = None
    anti_pick_reason: str | None = None
    trade_offs: list[TradeOff] = Field(default_factory=list)


@dataclass
class _Scored:
    """Internal per-candidate carrier: the public breakdown plus the raw values
    and per-field goodness (0..1) that trade-off extraction needs."""

    breakdown: ScoreBreakdown
    goodness: dict[str, float | None] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def sku(self) -> str:
        return self.breakdown.sku

    @property
    def total(self) -> float:
        return self.breakdown.total_score


# --------------------------------------------------------------------------- #
# Field helpers                                                              #
# --------------------------------------------------------------------------- #
def _priority_slot(slot_profile: SlotProfile) -> SlotDef | None:
    for slot in slot_profile.optional_slots:
        if slot.name == PRIORITY_SLOT_NAME:
            return slot
    return None


def _spec_fields(catalog_field: str | list[str] | None) -> list[str]:
    """Extract bare spec field names (``specs.inverter`` → ``inverter``).

    Non-``specs.*`` mappings (e.g. ``price.sale_price``) are intentionally
    dropped — those are handled as bonus/penalty, not `match` criteria.
    """
    if catalog_field is None:
        return []
    entries = [catalog_field] if isinstance(catalog_field, str) else catalog_field
    out: list[str] = []
    for entry in entries:
        if entry.startswith(_SPEC_FIELD_PREFIX):
            name = entry[len(_SPEC_FIELD_PREFIX) :]
            if name not in out:
                out.append(name)
    return out


def _stated_values(profile: NeedProfile) -> list[str]:
    raw = profile.slots.get(PRIORITY_SLOT_NAME)
    if isinstance(raw, list):
        return [str(v) for v in raw]
    if raw:
        return [str(raw)]
    return []


def _stated_fields(criterion_fields: list[str], stated_values: list[str]) -> set[str]:
    stated: set[str] = set()
    for name in criterion_fields:
        for value in stated_values:
            if any(kw in name for kw in _PRIORITY_FIELD_KEYWORDS.get(value, ())):
                stated.add(name)
                break
    return stated


def _lower_is_better(name: str) -> bool:
    low = name.lower()
    return any(token in low for token in ("noise", "price", "cost", "consum"))


def _numeric(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _goodness(name: str, value: Any, fmin: float, fmax: float) -> float | None:
    """Map a raw spec value to a 0..1 'goodness'. ``None`` = missing/unrankable."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not _numeric(value):
        return None  # present but not numerically comparable (e.g. gas_type)
    if fmax == fmin:
        return 1.0  # no spread across the set → neutral, constant across candidates
    span = fmax - fmin
    if _lower_is_better(name):
        return (fmax - value) / span
    return (value - fmin) / span


# --------------------------------------------------------------------------- #
# Scoring                                                                    #
# --------------------------------------------------------------------------- #
def _score_all(
    candidates: list[dict[str, Any]],
    criterion_fields: list[str],
    stated_fields: set[str],
    budget: float | None,
) -> list[_Scored]:
    # Min-max bounds per numeric field, computed across the set this turn.
    bounds: dict[str, tuple[float, float]] = {}
    for name in criterion_fields:
        nums = [
            c.get("specs", {}).get(name)
            for c in candidates
            if _numeric(c.get("specs", {}).get(name))
        ]
        if nums:
            bounds[name] = (min(nums), max(nums))

    scored: list[_Scored] = []
    for cand in candidates:
        specs = cand.get("specs") or {}
        price = cand.get("price")
        per_criterion: dict[str, float] = {}
        missing: list[str] = []
        goodness: dict[str, float | None] = {}
        raw: dict[str, Any] = {}

        for name in criterion_fields:
            value = specs.get(name)
            raw[name] = value
            weight = STATED_PRIORITY_WEIGHT if name in stated_fields else UNSTATED_WEIGHT
            fmin, fmax = bounds.get(name, (0.0, 0.0))
            good = _goodness(name, value, fmin, fmax)
            goodness[name] = good
            if value is None:
                missing.append(name)
                per_criterion[name] = 0.0
                if name in stated_fields:
                    per_criterion[_PENALTY_MISSING_PREFIX + name] = -MISSING_STATED_FIELD_PENALTY
            else:
                per_criterion[name] = weight * (good if good is not None else 0.0)

        # Bonuses — small, fixed, only when the signal is actually present.
        if price is not None:
            per_criterion[_BONUS_PRICE_KEY] = PRICE_PRESENT_BONUS
        if cand.get("in_stock"):  # None (unknown) stays neutral — never penalized
            per_criterion[_BONUS_STOCK_KEY] = IN_STOCK_BONUS

        # Soft over-budget penalty (deprioritize, never exclude).
        if budget is not None and price is not None and price > budget:
            per_criterion[_PENALTY_OVER_BUDGET_KEY] = -OVER_BUDGET_PENALTY

        total = sum(per_criterion.values())
        scored.append(
            _Scored(
                breakdown=ScoreBreakdown(
                    sku=str(cand.get("sku")),
                    total_score=total,
                    per_criterion=per_criterion,
                    missing_fields=missing,
                    price=price,
                ),
                goodness=goodness,
                raw=raw,
            )
        )
    return scored


def _rank_key(s: _Scored) -> tuple[float, str]:
    # Best first; deterministic sku tie-break so ordering is stable.
    return (-s.total, s.sku)


# --------------------------------------------------------------------------- #
# Anti-pick                                                                  #
# --------------------------------------------------------------------------- #
def _anti_pick(scored: list[_Scored], criterion_fields: list[str]) -> tuple[_Scored, str]:
    priced = [s for s in scored if s.breakdown.price is not None]
    pool = priced or scored
    worst = min(pool, key=lambda s: (s.total, s.sku))

    weak = _weakest_criterion(worst, criterion_fields)
    if priced:
        reason = (
            f"Điểm phù hợp thấp nhất ({worst.total:.2f}) trong nhóm sản phẩm có giá — "
            f"khách dễ chú ý vì hiển thị giá, nhưng yếu nhất ở {weak} so với nhu cầu."
        )
    else:
        reason = (
            f"Không sản phẩm nào có dữ liệu giá; lấy điểm phù hợp thấp nhất toàn cục "
            f"({worst.total:.2f}), yếu nhất ở {weak}."
        )
    return worst, reason


def _weakest_criterion(s: _Scored, criterion_fields: list[str]) -> str:
    rankable = {n: g for n in criterion_fields if (g := s.goodness.get(n)) is not None}
    if not rankable:
        return "dữ liệu"
    return min(rankable, key=lambda n: (rankable[n], n))


# --------------------------------------------------------------------------- #
# Trade-offs                                                                 #
# --------------------------------------------------------------------------- #
def _trade_offs(top: list[_Scored], pool: list[str]) -> list[TradeOff]:
    result: list[TradeOff] = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i], top[j]
            a_wins: list[str] = []
            b_wins: list[str] = []
            for name in pool:
                ga, gb = a.goodness.get(name), b.goodness.get(name)
                if ga is None or gb is None or ga == gb:
                    continue
                (a_wins if ga > gb else b_wins).append(name)
            # A genuine trade-off requires the advantage direction to reverse.
            if a_wins and b_wins:
                cited = sorted(set(a_wins) | set(b_wins))
                result.append(
                    TradeOff(
                        sku_a=a.sku,
                        sku_b=b.sku,
                        a_wins_on=sorted(a_wins),
                        b_wins_on=sorted(b_wins),
                        values={name: (a.raw.get(name), b.raw.get(name)) for name in cited},
                    )
                )
    return result


# --------------------------------------------------------------------------- #
# Public entry point                                                         #
# --------------------------------------------------------------------------- #
def rank_candidates(
    candidates: list[dict[str, Any]],
    profile: NeedProfile,
    slot_profile: SlotProfile,
) -> RankingResult:
    """Rank candidate dicts into top-3 + one anti-pick + pairwise trade-offs.

    Pure and deterministic: identical inputs always yield identical output,
    including tie-break order (by ``sku``).
    """
    if not candidates:
        return RankingResult(top=[], anti_pick=None, anti_pick_reason=None, trade_offs=[])

    priority = _priority_slot(slot_profile)
    criterion_fields = _spec_fields(priority.catalog_field) if priority is not None else []
    stated_values = _stated_values(profile)
    stated = _stated_fields(criterion_fields, stated_values)

    budget_raw = profile.slots.get(BUDGET_SLOT_NAME)
    budget = float(budget_raw) if isinstance(budget_raw, int | float) else None

    scored = _score_all(candidates, criterion_fields, stated, budget)
    scored.sort(key=_rank_key)

    top = scored[:3]
    # Trade-offs cite stated criteria; with nothing stated, fall back to the
    # full criterion set so top candidates are still comparable.
    pool = sorted(stated) if stated else criterion_fields
    trade_offs = _trade_offs(top, pool)

    anti_pick: ScoreBreakdown | None = None
    anti_reason: str | None = None
    if len(scored) >= 2:
        worst, anti_reason = _anti_pick(scored, criterion_fields)
        anti_pick = worst.breakdown

    return RankingResult(
        top=[s.breakdown for s in top],
        anti_pick=anti_pick,
        anti_pick_reason=anti_reason,
        trade_offs=trade_offs,
    )
