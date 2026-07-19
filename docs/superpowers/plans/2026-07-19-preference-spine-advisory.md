# Preference-Spine Advisory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the customer's stated preferences flow through extraction → filtering → ranking → card copy so the advisory cards show real, differentiated trade-offs and benefits (not boilerplate) for every category that has parsed spec data, and stay honest (no fake "100%", no negatives shown as strengths) for every category.

**Architecture:** Generalize S5 ranking from a hard-coded `uu_tien`-only criteria source to a declarative `ranking_criteria` block (with explicit direction semantics) plus a graceful fallback; bridge S2 so "tiết kiệm điện" sets the energy slot; make the energy preference a soft S5 signal instead of an S4 hard filter; and make all card copy deterministic and honest.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0, pytest. All pipeline stages are pure functions (no DB/LLM/I-O) except S4 (`catalog_search`, SQLAlchemy) and the service shell.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-19-preference-spine-advisory-design.md`.
- Working directory for all commands: `/home/tuanjhg/Work/VAIC/apps/api`.
- Run tests with the repo venv: `python -m pytest` (from `apps/api`).
- Vietnamese copy strings: keep the "em"/"anh/chị" voice, no markdown, no hype words.
- Only reference **parsed** `specs.*` fields in `ranking_criteria` — never `specs_raw.*` (unparsed strings). The 9 raw-only categories get presentation honesty only, no criteria.
- Preserve behavior of the 4 `uu_tien` categories (`may_lanh`, `may_giat`, `may_rua_chen`, `dong_ho_tm`) exactly — they have no `ranking_criteria`, so they must keep flowing through the legacy `uu_tien` path unchanged.
- Determinism: S5 is a pure function; identical inputs must yield identical output including sku tie-break order.
- End each commit message with the Co-Authored-By trailer already used in this repo's history (`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`).

---

## File Structure

- `src/pipeline/slots/__init__.py` — add `RankingCriterion` model + `ranking_criteria` field on `SlotProfile`. (Task 1)
- `src/pipeline/slots/tu_lanh.yaml` — add the `ranking_criteria` block. (Task 1)
- `src/pipeline/s5_ranking.py` — the ranking generalization: `Criterion`, `_criteria_for`, direction-explicit goodness, `target` right-sizing, wiring. (Tasks 2, 3)
- `src/pipeline/s2_extract.py` — energy-phrase → `inverter` bridge in `_overlay_text_slots`. (Task 4)
- `src/tools/catalog_search.py` — make `inverter` a soft signal (drop hard filter). (Task 5)
- `src/services/advisor_chat_service.py` — presentation honesty: strengths filter, match-score tie, honest trade-off fallback, deterministic reason. (Tasks 6, 7)
- Tests: `tests/test_s5_ranking.py`, `tests/test_s2_extract.py`, `tests/test_catalog_search.py`, `tests/test_chat_advisor.py`.

---

## Task 1: `ranking_criteria` schema + tu_lanh criteria

**Files:**
- Modify: `src/pipeline/slots/__init__.py:36-61`
- Modify: `src/pipeline/slots/tu_lanh.yaml` (append a `ranking_criteria:` block)
- Test: `tests/test_slots.py`

**Interfaces:**
- Produces: `SlotProfile.ranking_criteria: list[RankingCriterion]` where
  `RankingCriterion(field: str, direction: str, target: str | None = None)`.
  `direction` ∈ `{"higher_better","lower_better","boolean_pref","target"}`.
  Empty list when the YAML omits the block.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_slots.py`:

```python
from src.pipeline.slots import load_slot_profile


def test_tu_lanh_declares_ranking_criteria():
    profile = load_slot_profile("tu_lanh")
    by_field = {c.field: c for c in profile.ranking_criteria}
    assert by_field["inverter"].direction == "boolean_pref"
    cap = by_field["capacity_total_l"]
    assert cap.direction == "target"
    assert cap.target == "dung_tich_can"


def test_may_lanh_has_no_ranking_criteria():
    # uu_tien categories keep the legacy path; the field defaults to empty.
    assert load_slot_profile("may_lanh").ranking_criteria == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slots.py::test_tu_lanh_declares_ranking_criteria -v`
Expected: FAIL (`AttributeError`/validation: `SlotProfile` has no `ranking_criteria`, or empty).

- [ ] **Step 3: Add the model + field**

In `src/pipeline/slots/__init__.py`, after `class DerivationRule` (line 48-50) add:

```python
class RankingCriterion(BaseModel):
    """One S5 fit-score criterion with explicit ranking semantics.

    ``direction`` fixes how the raw spec value maps to 0..1 goodness:
    ``higher_better`` / ``lower_better`` (numeric, min-max across the set),
    ``boolean_pref`` (True is the good pole), ``target`` (closeness to a derived
    need — bigger-than-need is worse). ``target`` names a derivation rule S5
    knows how to compute (e.g. ``dung_tich_can``).
    """

    field: str
    direction: Literal["higher_better", "lower_better", "boolean_pref", "target"]
    target: str | None = None
```

Then add to `class SlotProfile` (after `catalog_field_map`, line 60):

```python
    ranking_criteria: list[RankingCriterion] = []
```

- [ ] **Step 4: Add the tu_lanh block**

Append to `src/pipeline/slots/tu_lanh.yaml` (after `catalog_field_map:`):

```yaml
ranking_criteria:
  - field: inverter
    direction: boolean_pref
  - field: capacity_total_l
    direction: target
    target: dung_tich_can
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_slots.py -v`
Expected: PASS (both new tests, plus existing slot tests still green).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/slots/__init__.py src/pipeline/slots/tu_lanh.yaml tests/test_slots.py
git commit -m "feat(s5): declare ranking_criteria schema + tu_lanh criteria

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: S5 criteria derivation + direction-explicit goodness

**Files:**
- Modify: `src/pipeline/s5_ranking.py` (add `Criterion`, `_criteria_for`, `_goodness_for`; rewire `_score_all` + `rank_candidates`)
- Test: `tests/test_s5_ranking.py`

**Interfaces:**
- Consumes: `SlotProfile.ranking_criteria` (Task 1).
- Produces:
  - `@dataclass(frozen=True) Criterion(field: str, direction: str, target: str | None = None)`
  - `_criteria_for(slot_profile: SlotProfile, profile: NeedProfile) -> tuple[list[Criterion], set[str]]` (criteria, stated-field set)
  - `_goodness_for(criterion: Criterion, value: Any, bounds: tuple[float,float], need: float | None) -> float | None`
  - `_score_all(candidates, criteria: list[Criterion], stated_fields, budget, needs: dict[str,float], legacy_capacity_need: float | None) -> list[_Scored]`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_s5_ranking.py`:

```python
TU_LANH_PROFILE = load_slot_profile("tu_lanh")


def _tl_profile(**slots):
    return NeedProfile(category="tu_lanh", slots=dict(slots))


def _tl_cand(sku, *, price=10_000_000, **specs):
    return {"sku": sku, "name": f"Tủ lạnh {sku}", "specs": dict(specs), "price": price,
            "in_stock": None}


def test_tu_lanh_inverter_preference_ranks_inverter_first():
    # Two otherwise-equal fridges; only inverter differs. Energy stated => 3x.
    cands = [
        _tl_cand("NONINV", inverter=False, capacity_total_l=240),
        _tl_cand("INV", inverter=True, capacity_total_l=240),
    ]
    result = rank_candidates(cands, _tl_profile(so_nguoi_dung=3, inverter=True), TU_LANH_PROFILE)
    assert result.top[0].sku == "INV"


def test_tu_lanh_criteria_come_from_ranking_criteria_not_uu_tien():
    cands = [_tl_cand("X", inverter=True, capacity_total_l=240)]
    result = rank_candidates(cands, _tl_profile(so_nguoi_dung=3, inverter=True), TU_LANH_PROFILE)
    fields = {k for k in result.top[0].per_criterion if ":" not in k}
    assert "inverter" in fields and "capacity_total_l" in fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_s5_ranking.py::test_tu_lanh_inverter_preference_ranks_inverter_first -v`
Expected: FAIL (currently tu_lanh has empty `criterion_fields`; INV and NONINV tie and sku tie-break puts "INV" second — assert fails, or per_criterion lacks `inverter`).

- [ ] **Step 3: Add `Criterion` + derivation + goodness**

In `src/pipeline/s5_ranking.py`, after the `_Scored` dataclass (line ~185-200) add:

```python
@dataclass(frozen=True)
class Criterion:
    """One ranking criterion with explicit direction (see RankingCriterion)."""

    field: str
    direction: str
    target: str | None = None


def _need_for_target(target_rule: str, profile: NeedProfile) -> float | None:
    """Compute the target 'need' for a right-sizing criterion, or None.

    ``dung_tich_can`` mirrors S4's tủ lạnh sizing (``45*so_nguoi + 100``), so
    ranking and hard-filter agree on the same number.
    """
    if target_rule == "dung_tich_can":
        people = profile.slots.get("so_nguoi_dung")
        if isinstance(people, int | float) and not isinstance(people, bool):
            return 45.0 * float(people) + 100.0
    return None


def _criteria_for(
    slot_profile: SlotProfile, profile: NeedProfile
) -> tuple[list[Criterion], set[str]]:
    """Derive ranking criteria + the stated-field set, category-agnostically.

    Priority: (1) declarative ``ranking_criteria``; (2) legacy ``uu_tien`` slot
    (unchanged behavior); (3) neither -> no criteria (raw categories degrade to
    an honest empty comparison).
    """
    if slot_profile.ranking_criteria:
        criteria = [
            Criterion(field=c.field, direction=c.direction, target=c.target)
            for c in slot_profile.ranking_criteria
        ]
        return criteria, _stated_criteria_fields(slot_profile, profile, criteria)

    priority = _priority_slot(slot_profile)
    if priority is not None:
        fields = _spec_fields(priority.catalog_field)
        criteria = [
            Criterion(field=f, direction="lower_better" if _lower_is_better(f) else "higher_better")
            for f in fields
        ]
        stated = _stated_fields(fields, _stated_values(profile))
        return criteria, stated

    return [], set()


def _stated_criteria_fields(
    slot_profile: SlotProfile, profile: NeedProfile, criteria: list[Criterion]
) -> set[str]:
    """A criterion is 'stated' (weighted 3x) when the customer supplied it: for a
    plain field, the slot mapping to it holds a value; for a ``target`` field, the
    derivation input is known (so right-sizing is meaningful)."""
    field_to_slot: dict[str, str] = {}
    for slot in [*slot_profile.required_slots, *slot_profile.optional_slots]:
        for f in _spec_fields(slot.catalog_field):
            field_to_slot.setdefault(f, slot.name)
    stated: set[str] = set()
    for c in criteria:
        if c.direction == "target":
            if c.target and _need_for_target(c.target, profile) is not None:
                stated.add(c.field)
        else:
            slot_name = field_to_slot.get(c.field)
            if slot_name is not None and profile.slots.get(slot_name) is not None:
                stated.add(c.field)
    return stated


def _goodness_for(
    criterion: Criterion, value: Any, bounds: tuple[float, float], need: float | None
) -> float | None:
    """Map a raw value to 0..1 goodness by the criterion's explicit direction.

    ``None`` = missing/unrankable. ``target`` = 1.0 within the tolerance band,
    declining as the value grows past ``need*OVERSIZE_TOLERANCE``.
    """
    if value is None:
        return None
    if criterion.direction == "target":
        if need is None or not _numeric(value):
            return None
        ratio = float(value) / need
        if ratio <= OVERSIZE_TOLERANCE:
            return 1.0
        return max(0.0, 1.0 - (ratio - OVERSIZE_TOLERANCE))
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not _numeric(value):
        return None
    fmin, fmax = bounds
    if fmax == fmin:
        return 1.0
    span = fmax - fmin
    if criterion.direction == "lower_better":
        return (fmax - value) / span
    return (value - fmin) / span
```

- [ ] **Step 4: Rewire `_score_all` to iterate criteria**

Replace the body of `_score_all` (currently `s5_ranking.py:294-373`) so its signature and criterion loop use `Criterion`:

```python
def _score_all(
    candidates: list[dict[str, Any]],
    criteria: list[Criterion],
    stated_fields: set[str],
    budget: float | None,
    needs: dict[str, float],
    legacy_capacity_need: float | None = None,
) -> list[_Scored]:
    # Min-max bounds only for numeric-directional criteria.
    numeric_fields = [c.field for c in criteria if c.direction in ("higher_better", "lower_better")]
    bounds: dict[str, tuple[float, float]] = {}
    for name in numeric_fields:
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

        for criterion in criteria:
            name = criterion.field
            value = specs.get(name)
            raw[name] = value
            weight = STATED_PRIORITY_WEIGHT if name in stated_fields else UNSTATED_WEIGHT
            good = _goodness_for(criterion, value, bounds.get(name, (0.0, 0.0)), needs.get(name))
            goodness[name] = good
            if value is None:
                missing.append(name)
                per_criterion[name] = 0.0
                if name in stated_fields:
                    per_criterion[_PENALTY_MISSING_PREFIX + name] = -MISSING_STATED_FIELD_PENALTY
            else:
                per_criterion[name] = weight * (good if good is not None else 0.0)

        if price is not None:
            per_criterion[_BONUS_PRICE_KEY] = PRICE_PRESENT_BONUS
        if cand.get("in_stock"):
            per_criterion[_BONUS_STOCK_KEY] = IN_STOCK_BONUS
        if budget is not None and price is not None and price > budget:
            per_criterion[_PENALTY_OVER_BUDGET_KEY] = -OVER_BUDGET_PENALTY

        # Legacy oversize penalty: only the uu_tien path (may_lanh) sets
        # legacy_capacity_need; target-criterion categories (tu_lanh) leave it
        # None so right-sizing is not double-counted.
        capacity = specs.get(_CAPACITY_FIELD)
        if (
            legacy_capacity_need
            and isinstance(capacity, int | float)
            and not isinstance(capacity, bool)
        ):
            ratio = capacity / legacy_capacity_need
            if ratio > OVERSIZE_TOLERANCE:
                per_criterion[_PENALTY_OVERSIZE_KEY] = -OVERSIZE_PENALTY * (ratio - OVERSIZE_TOLERANCE)

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
```

- [ ] **Step 5: Rewire `rank_candidates`**

Replace the criteria-computing lines in `rank_candidates` (currently `s5_ranking.py:456-465`) with:

```python
    criteria, stated = _criteria_for(slot_profile, profile)
    criterion_fields = [c.field for c in criteria]

    budget_raw = profile.slots.get(BUDGET_SLOT_NAME)
    budget = float(budget_raw) if isinstance(budget_raw, int | float) else None

    needs: dict[str, float] = {}
    for c in criteria:
        if c.direction == "target" and c.target:
            need = _need_for_target(c.target, profile)
            if need is not None:
                needs[c.field] = need

    legacy_capacity_need = _capacity_need(slot_profile, profile)
    scored = _score_all(candidates, criteria, stated, budget, needs, legacy_capacity_need)
    scored.sort(key=_rank_key)
```

(Everything after — `top = scored[:3]`, `pool`, `_trade_offs`, `_anti_pick` — stays as-is; `criterion_fields` and `stated` keep the same names those lines already use.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_s5_ranking.py -v`
Expected: PASS — the two new tu_lanh tests pass AND every existing may_lanh test stays green (legacy path unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/s5_ranking.py tests/test_s5_ranking.py
git commit -m "feat(s5): derive ranking criteria from ranking_criteria, not just uu_tien

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: S5 `target` right-sizing produces real trade-offs

**Files:**
- Modify: `src/pipeline/s5_ranking.py` (no new code expected; this task proves the `target` path yields trade-offs and add a test)
- Test: `tests/test_s5_ranking.py`

**Interfaces:**
- Consumes: `Criterion(direction="target")`, `_need_for_target`, `_goodness_for` (Task 2).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_s5_ranking.py`:

```python
def test_tu_lanh_right_sizing_beats_oversized_and_emits_tradeoff():
    # 3 people => need = 45*3+100 = 235L. RIGHT (~240L) is right-sized;
    # HUGE (500L) is >1.3x oversized. Both inverter (so capacity decides).
    cands = [
        _tl_cand("HUGE", inverter=True, capacity_total_l=500),
        _tl_cand("RIGHT", inverter=True, capacity_total_l=240),
    ]
    result = rank_candidates(cands, _tl_profile(so_nguoi_dung=3, inverter=True), TU_LANH_PROFILE)
    assert result.top[0].sku == "RIGHT"
    # A genuine trade-off between the two on capacity is emitted.
    fields = {f for t in result.trade_offs for f in (t.a_wins_on + t.b_wins_on)}
    assert "capacity_total_l" in fields


def test_tu_lanh_capacity_not_stated_when_household_unknown():
    # No so_nguoi_dung => capacity target is not a stated (3x) criterion.
    cands = [_tl_cand("X", inverter=True, capacity_total_l=240)]
    result = rank_candidates(cands, _tl_profile(inverter=True), TU_LANH_PROFILE)
    # capacity goodness is None (no need) => contributes 0, listed missing-free
    # only because value present; assert it did not get the stated penalty.
    assert not any(k.startswith("penalty:missing:capacity_total_l")
                   for k in result.top[0].per_criterion)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_s5_ranking.py::test_tu_lanh_right_sizing_beats_oversized_and_emits_tradeoff -v`
Expected: PASS if Task 2 is correct. If FAIL, the `target` goodness or `_trade_offs` pool is wrong — fix in `_goodness_for` / confirm `pool = sorted(stated)` includes `capacity_total_l` when household is known.

- [ ] **Step 3: Fix only if failing**

If the trade-off is absent: confirm `capacity_total_l` is in `stated` (household known) so it enters `pool`. No code change expected beyond Task 2; if `_goodness_for` returned 1.0 for both, verify `500/235 = 2.13 > 1.3` yields goodness `< 1.0` while `240/235 = 1.02 <= 1.3` yields `1.0`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_s5_ranking.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add tests/test_s5_ranking.py src/pipeline/s5_ranking.py
git commit -m "test(s5): tu_lanh right-sizing target yields ranking + trade-off

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: S2 — "tiết kiệm điện" bridges to the inverter slot

**Files:**
- Modify: `src/pipeline/s2_extract.py:537-568` (`_overlay_text_slots`)
- Test: `tests/test_s2_extract.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: after `_overlay_text_slots`, a tu_lanh turn whose text contains an
  energy-saving phrase (no literal "inverter") yields `slots["inverter"] == True`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_s2_extract.py` (match existing helpers there; if the file builds slots via `_overlay_text_slots` or `_reconcile_slots`, reuse that; otherwise call `deterministic_fallback` with a tu_lanh `S1Result`). Minimal direct test:

```python
from src.pipeline.s2_extract import _overlay_text_slots
from src.pipeline.slots import load_slot_profile


def _tu_lanh_slots():
    p = load_slot_profile("tu_lanh")
    return [*p.required_slots, *p.optional_slots]


def test_energy_phrase_sets_inverter_true_without_the_word_inverter():
    result: dict = {}
    _overlay_text_slots(result, _tu_lanh_slots(), "nhà 3 người cần tiết kiệm điện")
    assert result.get("inverter") is True


def test_negated_inverter_still_false():
    result: dict = {}
    _overlay_text_slots(result, _tu_lanh_slots(), "khong can inverter")
    assert result.get("inverter") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_s2_extract.py::test_energy_phrase_sets_inverter_true_without_the_word_inverter -v`
Expected: FAIL (`inverter` not set — "tiết kiệm điện" has no path to the inverter slot).

- [ ] **Step 3: Add the energy-phrase bridge**

In `src/pipeline/s2_extract.py`, above `_reconcile_slots` (near the `_ENUM_PHRASES` block ~line 410) add:

```python
# Energy-saving intent phrases that imply "prefer inverter" for categories whose
# energy lever is the boolean `inverter` slot (no literal "inverter" word needed).
_ENERGY_SAVING_PHRASES: tuple[str, ...] = ("tiet kiem dien", "it ton dien", "it hao dien")
```

Then in `_overlay_text_slots`, change the inverter branch (currently lines 564-568):

```python
        elif slot.type == "boolean" and slot.name == "inverter":
            if re.search(r"\bkhong\s+(?:can\s+)?inverter\b", folded):
                result[slot.name] = False
            elif "inverter" in folded or any(p in folded for p in _ENERGY_SAVING_PHRASES):
                result[slot.name] = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_s2_extract.py -v`
Expected: PASS (both new tests + existing S2 tests green).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/s2_extract.py tests/test_s2_extract.py
git commit -m "feat(s2): map 'tiết kiệm điện' to the inverter preference slot

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: S4 — inverter becomes a soft signal (no hard filter)

**Files:**
- Modify: `src/tools/catalog_search.py:230-248` (`_direct_conditions`)
- Test: `tests/test_catalog_search.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `catalog_search(..., slots={"inverter": True})` no longer excludes
  non-inverter products.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_catalog_search.py` (reuse the file's existing DB/session fixtures and product-seeding helpers — mirror an existing test that seeds tu_lanh products with `specs_json={"inverter": ...}`):

```python
def test_inverter_preference_is_soft_not_a_hard_filter(db_session):
    # Seed one inverter and one non-inverter tu_lanh product (reuse this file's
    # product factory / fixture names).
    _seed_tu_lanh(db_session, sku="INV", inverter=True)
    _seed_tu_lanh(db_session, sku="NONINV", inverter=False)

    result = catalog_search(db_session, category_key="tu_lanh", slots={"inverter": True})
    skus = {p.sku for p in result.products}
    assert {"INV", "NONINV"} <= skus  # non-inverter is NOT filtered out
```

(If the file has no `_seed_tu_lanh`, add a tiny local helper alongside the existing seeding pattern in that test module.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog_search.py::test_inverter_preference_is_soft_not_a_hard_filter -v`
Expected: FAIL (`NONINV` excluded — inverter is currently a hard filter).

- [ ] **Step 3: Skip inverter in the hard filter**

In `src/tools/catalog_search.py`, add near the module constants (after `_DERIVATION_SLOT_KEYS`, line 56):

```python
# Quality-preference fields scored softly in S5, never hard-filtered — showing a
# cheaper/right-sized alternative with an honest trade-off beats over-filtering.
_SOFT_PREFERENCE_FIELDS = frozenset({"inverter"})
```

Then in `_direct_conditions`, skip those fields (inside the loop, after resolving `json_key`, lines 241-248):

```python
        json_key = _json_key(field_map, key)
        if json_key is None:
            continue
        if json_key in _SOFT_PREFERENCE_FIELDS:
            continue  # soft signal (S5), not a hard filter
        if isinstance(value, bool):
            conditions.append(Product.specs_json[json_key].as_boolean() == value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_catalog_search.py -v`
Expected: PASS (new test passes; update any pre-existing test that asserted inverter WAS hard-filtered — change it to assert the new soft behavior, since the product decision is "soft"). Budget and capacity-filter tests must stay green.

- [ ] **Step 5: Commit**

```bash
git add src/tools/catalog_search.py tests/test_catalog_search.py
git commit -m "feat(s4): treat inverter as a soft preference, not a hard filter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Cards — strengths filter, honest match-score, honest trade-off fallback

**Files:**
- Modify: `src/services/advisor_chat_service.py` (`_strengths` 407-413, `_match_scores` 364-375, `_trade_off_text` final return 404)
- Test: `tests/test_chat_advisor.py`

**Interfaces:**
- Produces: `_match_scores` returns equal `_TIE_SCORE` values when the top spread
  is within `_TIE_RATIO`; `_strengths` drops `False`-valued boolean specs;
  `_trade_off_text` returns the honest "chưa đủ dữ liệu" string when a card has no
  ranking criteria.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_chat_advisor.py`:

```python
from src.services.advisor_chat_service import _match_scores, _strengths, _trade_off_text
from src.pipeline.s5_ranking import RankingResult, ScoreBreakdown


def test_strengths_drops_false_boolean_specs():
    # inverter=False must NOT appear as a strength.
    out = _strengths({"inverter": False, "capacity_total_l": 235})
    assert all("không phải inverter" not in s for s in out)
    assert any("235" in s for s in out)


def test_match_scores_tie_avoids_triple_hundred():
    top = [ScoreBreakdown(sku="A", total_score=1.0),
           ScoreBreakdown(sku="B", total_score=1.0),
           ScoreBreakdown(sku="C", total_score=1.0)]
    assert _match_scores(top) == [75, 75, 75]


def test_match_scores_keeps_spread_when_differentiated():
    top = [ScoreBreakdown(sku="A", total_score=1.0),
           ScoreBreakdown(sku="B", total_score=0.5)]
    assert _match_scores(top) == [100, 50]


def test_trade_off_honest_when_no_criteria():
    # No trade_offs, no missing, no per_criterion bare fields (raw category).
    ranking = RankingResult(top=[ScoreBreakdown(sku="A", total_score=0.05)], trade_offs=[])
    bd = ScoreBreakdown(sku="A", total_score=0.05, per_criterion={"bonus:price_available": 0.05})
    text = _trade_off_text("A", ranking, bd)
    assert "bảo hành và chi phí lắp đặt" not in text
    assert "chưa đủ dữ liệu" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_chat_advisor.py -k "strengths_drops or match_scores_tie or trade_off_honest" -v`
Expected: FAIL (strengths includes the negative; `_match_scores` returns `[100,100,100]`; trade-off returns the old boilerplate).

- [ ] **Step 3: Implement the three fixes**

In `src/services/advisor_chat_service.py`:

Add constants near `_CARD_LABELS` (line 90):

```python
_TIE_RATIO = 0.02  # top scores within 2% of the best => "undifferentiated"
_TIE_SCORE = 75    # honest equal score instead of a misleading 100/100/100
```

Replace `_match_scores` (364-375):

```python
def _match_scores(top: list[ScoreBreakdown]) -> list[int]:
    """Relative fit percent of the best score. When the top scores are within
    ``_TIE_RATIO`` of each other (nothing meaningfully separates them — e.g. a
    raw category with no criteria) return an equal, honest ``_TIE_SCORE`` rather
    than three misleading 100%s."""
    if not top:
        return []
    scores = [b.total_score for b in top]
    best = max(scores)
    if best <= 0:
        return [max(50, 90 - 10 * i) for i in range(len(top))]
    if (best - min(scores)) / best <= _TIE_RATIO:
        return [_TIE_SCORE for _ in top]
    return [max(50, min(100, round(100 * s / best))) for s in scores]
```

Replace `_strengths` (407-413):

```python
def _strengths(specs: dict[str, Any]) -> list[str]:
    """Positive, plain-language highlights. A ``False`` boolean spec (e.g.
    ``inverter=False``) is never a strength — it belongs in the trade-off, not
    the pros list."""
    phrases = [
        rendered
        for field, value in specs.items()
        if value is not False and (rendered := render_spec(field, value)) is not None
    ]
    return phrases[:3]
```

Replace the final `return` of `_trade_off_text` (line 404):

```python
    return (
        "Chưa đủ dữ liệu cấu trúc để nêu đánh đổi cụ thể; "
        "anh/chị nên xem chi tiết sản phẩm để so sánh thêm"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chat_advisor.py -v`
Expected: PASS. Update any existing advisor test that asserted the old boilerplate trade-off string or a `100` tie score.

- [ ] **Step 5: Commit**

```bash
git add src/services/advisor_chat_service.py tests/test_chat_advisor.py
git commit -m "fix(cards): honest match score, drop false-boolean strengths, honest empty trade-off

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Cards — deterministic per-card benefit (`reason`)

**Files:**
- Modify: `src/services/advisor_chat_service.py` (`_build_cards` 416-444; add `_reason_text`)
- Test: `tests/test_chat_advisor.py`

**Interfaces:**
- Consumes: `ScoreBreakdown.per_criterion` (Task 2 populates it for tu_lanh),
  `render_spec` (already imported line 33).
- Produces: `_reason_text(breakdown: ScoreBreakdown, specs: dict[str, Any]) -> str`.
  `reason` no longer reads `result.advice.statements`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_chat_advisor.py`:

```python
from src.services.advisor_chat_service import _reason_text


def test_reason_is_deterministic_from_strongest_criterion():
    bd = ScoreBreakdown(sku="A", total_score=3.05,
                        per_criterion={"inverter": 3.0, "bonus:price_available": 0.05})
    text = _reason_text(bd, {"inverter": True})
    assert "đỡ tốn điện" in text          # rendered from the inverter glossary phrase
    assert "Phù hợp" in text


def test_reason_falls_back_when_no_positive_criterion():
    bd = ScoreBreakdown(sku="A", total_score=0.05,
                        per_criterion={"bonus:price_available": 0.05})
    text = _reason_text(bd, {})
    assert "Phù hợp với nhu cầu đã nêu" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chat_advisor.py::test_reason_is_deterministic_from_strongest_criterion -v`
Expected: FAIL (`_reason_text` does not exist).

- [ ] **Step 3: Add `_reason_text` and use it in `_build_cards`**

In `src/services/advisor_chat_service.py`, add above `_build_cards` (line 416):

```python
def _reason_text(breakdown: ScoreBreakdown, specs: dict[str, Any]) -> str:
    """Deterministic per-card benefit: render the card's strongest positive
    criterion via the glossary. Independent of the LLM prose (which the verifier
    may drop), so the benefit never collapses to a generic line when data exists."""
    positives = {
        field: score
        for field, score in breakdown.per_criterion.items()
        if ":" not in field and score > 0
    }
    if positives:
        best = max(positives, key=lambda field: (positives[field], field))
        phrase = render_spec(best, specs.get(best))
        if phrase is not None:
            return "Phù hợp vì " + phrase
    return "Phù hợp với nhu cầu đã nêu dựa trên thông tin sản phẩm hiện có."
```

Then in `_build_cards`, remove the `statements`-based reason. Replace lines 419 and 424-427:

```python
    by_sku = {str(c.get("sku")): c for c in result.candidates}
    scores = _match_scores(result.ranking.top)

    cards: list[AdvisorCard] = []
    for index, breakdown in enumerate(result.ranking.top):
        cand = by_sku.get(breakdown.sku, {})
        reason = _reason_text(breakdown, cand.get("specs") or {})
```

(Delete the now-unused `statements = ...` line and the `_MARKER_PREFIX_RE` override block. Keep the rest of the `AdvisorCard(...)` construction; `reason=reason` still passes.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chat_advisor.py -v`
Expected: PASS. If `_MARKER_PREFIX_RE` is now unused, either remove it or leave it (a lint run in Task 9 will flag unused imports/vars — remove then).

- [ ] **Step 5: Commit**

```bash
git add src/services/advisor_chat_service.py tests/test_chat_advisor.py
git commit -m "fix(cards): deterministic per-card benefit from strongest criterion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: End-to-end advisory scenario (tu_lanh)

**Files:**
- Test: `tests/test_chat_advisor.py` (integration-level, uses the service with fakes as the file already does)

**Interfaces:**
- Consumes: the full pipeline via `AdvisorChatService` / `run_turn` fakes already
  present in this test module. Follow the module's existing fixture pattern for a
  fake router + seeded catalog.

- [ ] **Step 1: Write the failing/scenario test**

Add to `tests/test_chat_advisor.py`, mirroring the module's existing end-to-end test setup (fake router returning a valid S2 extraction + S6 prose, seeded tu_lanh candidates incl. one inverter + one non-inverter):

```python
async def test_tu_lanh_energy_request_end_to_end(advisor_service_with_tu_lanh):
    # "cần tiết kiệm điện" => inverter preferred, both shown, cards differentiated.
    resp = await advisor_service_with_tu_lanh.reply(
        _msg("nhà 3 người, 15 triệu, ngăn đá dưới, cần tiết kiệm điện")
    )
    assert resp.response_type == "recommendations"
    # inverter card ranks first
    assert resp.cards[0].specs.get("inverter") is True
    # no card shows a negative as a strength
    for card in resp.cards:
        assert all("không phải inverter" not in s for s in card.strengths)
    # benefits are not the old generic-only boilerplate for the top (data-rich) card
    assert resp.cards[0].reason != "Phù hợp với nhu cầu đã nêu dựa trên thông tin sản phẩm hiện có."
```

(Use the module's real message/factory helpers; `advisor_service_with_tu_lanh` should follow the existing fixture that wires a fake router + in-memory catalog. If no such fixture exists, build it from the existing single-category fixture in this file.)

- [ ] **Step 2: Run it to verify it fails first (red), then passes after wiring**

Run: `python -m pytest tests/test_chat_advisor.py::test_tu_lanh_energy_request_end_to_end -v`
Expected: initially FAIL if the fixture/seed isn't present; once the fixture seeds an inverter + non-inverter tu_lanh pair and Tasks 2–7 are in, it PASSES.

- [ ] **Step 3: Adjust fixture/seed only (no product-code changes)**

If failing due to missing seed data, extend the test fixture to seed the two tu_lanh candidates. No changes to `src/` should be needed here — this task validates the integrated behavior.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chat_advisor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_chat_advisor.py
git commit -m "test(advisor): end-to-end tu_lanh energy-saving scenario

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Full-suite regression + lint

**Files:**
- No new source; fix any regressions surfaced.

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest`
Expected: PASS. Pay special attention to `tests/test_s5_ranking.py` (4 uu_tien behavior unchanged), `tests/test_s6_generate.py`, `tests/test_catalog_search.py`, `tests/test_s8_respond.py`.

- [ ] **Step 2: Fix regressions**

For each failure, decide: is it an intended contract change (update the test to the new honest behavior — e.g. old inverter hard-filter assertion, old trade-off boilerplate string, old `100` tie score) or a real regression (fix the code)? Do not weaken a test to hide a real regression.

- [ ] **Step 3: Lint / type-check**

Run: `ruff check src tests && mypy src` (or the repo's configured commands — see `Makefile`).
Expected: clean. Remove any now-unused symbols (e.g. `_MARKER_PREFIX_RE` if Task 7 orphaned it).

- [ ] **Step 4: Verify the reported scenario by hand**

Follow `verify` skill guidance: drive a tu_lanh advisory turn ("nhà 3 người, 15 triệu, cần tiết kiệm điện") through the running service/tests and confirm: inverter cards on top, differentiated `reason` + `trade_off`, no "không phải inverter" in strengths, no triple-100%.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: regression sweep + lint for preference-spine advisory

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §4.1 S5 criteria mechanism → Tasks 1, 2, 3. ✓
- §4.2 S2 bridge → Task 4. ✓
- §4.3 S4 inverter soft → Task 5. ✓
- §4.4 presentation (strengths, reason, trade-off fallback, match-score) → Tasks 6, 7. ✓
- §5 testing → each task's tests + Task 8 (integration) + Task 9 (regression). ✓
- §6 risks (inverter regression, no double-count oversize, uu_tien unchanged) → Task 2 (legacy path preserved), Task 5 (test update), Task 9 (regression sweep). ✓
- Decision "spine for 5 parsed / honesty for 9 raw" → Tasks 6–7 apply to all; raw categories get empty criteria (Task 2 fallback) + honest trade-off/reason fallbacks. ✓

**Type consistency:** `Criterion(field, direction, target)` used identically across Tasks 2–3; `_criteria_for -> (list[Criterion], set[str])`, `_score_all(..., criteria, stated, budget, needs, legacy_capacity_need)`, `_reason_text(breakdown, specs)`, `_match_scores(top)` consistent across tasks.

**Placeholder scan:** all steps contain concrete code/commands. No TBD/TODO.
