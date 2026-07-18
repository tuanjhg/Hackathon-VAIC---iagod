"""S3 — dialogue policy ("hỏi ngược thông minh"), ADR C3.

Decides, given the current :class:`~src.pipeline.need_profile.NeedProfile` and a
pre-filter candidate count, whether the assistant should ask a clarifying
question (and which slots) or proceed straight to retrieval. This is the 10%
"smart clarifying-question" logic of the workflow doc §3 "S3".

Three ambiguity levels are derived from ``candidate_count`` (a plain ``int``
produced by the separate catalog_search pre-filter — this module never touches
a database) together with which slots are still fillable:

===== ============================================================ =============
Level Condition                                                    Action
===== ============================================================ =============
Cao   a required slot is unfilled, OR candidate_count > 20         ask 2-3 slots
Vừa   all required filled AND 6 <= candidate_count <= 20           ask 1 slot
Thấp  candidate_count <= 5, OR clarify quota exhausted, OR         proceed
      nothing left to ask
===== ============================================================ =============

Hard constraints enforced regardless of level:

* never select a slot where :meth:`NeedProfile.should_ask` is ``False``;
* at most :data:`MAX_ASK_BATCH` slots per question;
* deciding to ask consumes one clarify round via
  :meth:`NeedProfile.increment_clarify_round`; if the quota is already
  exhausted (it returns ``False``) the decision is downgraded to *proceed*
  rather than asking anyway.

Slot ordering for a question is: required slots first (in profile order), then
optional slots by ``priority_rank`` ascending (``None`` rank last). This uses
the hand-authored ``priority_rank`` from the slot YAML; wiring in the
data-driven information-gain scores from
``scripts/compute_information_gain.py`` as an override is future work and out of
scope here.
"""

from typing import Literal

from pydantic import BaseModel

from .need_profile import NeedProfile
from .slots import SlotDef, SlotProfile, load_slot_profile

LOW_CANDIDATE_THRESHOLD = 5
"""``candidate_count <= 5`` -> Thấp: the pre-filter already narrowed enough."""

HIGH_CANDIDATE_THRESHOLD = 20
"""``candidate_count > 20`` -> Cao: too broad, must narrow before retrieval."""

MAX_ASK_BATCH = 3
"""Hard cap on slots gathered into a single clarifying question."""


class PolicyDecision(BaseModel):
    """Outcome of :func:`decide_policy`, consumed by the question-builder.

    ``slots_to_ask`` is empty when ``action == "proceed"``. ``question_reason``
    is a caller-facing justification joined from the selected slots'
    ``rationale`` (falling back to ``label``) and is ``None`` when proceeding.
    ``proceeded_with_assumptions`` lists the names of required slots for which a
    stated default was recorded on the profile because the clarify quota ran out
    before they could be filled.
    """

    level: Literal["cao", "vua", "thap"]
    action: Literal["ask", "proceed"]
    slots_to_ask: list[SlotDef] = []
    question_reason: str | None = None
    proceeded_with_assumptions: list[str] = []


def _optional_by_priority(slots: list[SlotDef]) -> list[SlotDef]:
    """Optional slots ordered by ``priority_rank`` ascending, ``None`` last."""
    return sorted(
        slots,
        key=lambda s: (s.priority_rank is None, s.priority_rank if s.priority_rank is not None else 0),
    )


def _question_reason(slots: list[SlotDef]) -> str:
    """Join selected slots' rationale/label into one caller-facing reason."""
    return "; ".join(slot.rationale or slot.label for slot in slots)


def _default_assumption(slot: SlotDef) -> str:
    """An explicit, stated default for a required slot left unfilled when the
    clarify quota is exhausted ("đề xuất với giả định mặc định nêu rõ")."""
    if slot.values:
        return f"Giả định {slot.label.lower()}: mặc định '{slot.values[0]}' (chưa xác nhận)."
    return f"Giả định {slot.label.lower()}: dùng mức phổ biến mặc định (chưa xác nhận)."


def _proceed(
    profile: NeedProfile, missing_required: list[SlotDef]
) -> PolicyDecision:
    """Build a Thấp *proceed* decision, recording a stated default for each
    still-missing required slot so retrieval is never blocked."""
    assumed: list[str] = []
    for slot in missing_required:
        profile.add_assumption(_default_assumption(slot))
        assumed.append(slot.name)
    return PolicyDecision(
        level="thap",
        action="proceed",
        slots_to_ask=[],
        question_reason=None,
        proceeded_with_assumptions=assumed,
    )


def decide_policy(profile: NeedProfile, candidate_count: int) -> PolicyDecision:
    """Decide the S3 dialogue action for ``profile`` given ``candidate_count``.

    ``candidate_count`` is the SQL ``COUNT`` from the pre-filter (supplied by the
    catalog_search tool). Loads the :class:`SlotProfile` for ``profile.category``
    internally; raises :class:`ValueError` if the category is unknown, since S3
    only runs once a category has been detected.
    """
    if profile.category is None:
        raise ValueError("decide_policy requires profile.category to be set (S3 runs after category detection)")

    slot_profile: SlotProfile = load_slot_profile(profile.category)

    missing_required = [s for s in slot_profile.required_slots if profile.should_ask(s.name)]
    askable_optional = [s for s in slot_profile.optional_slots if profile.should_ask(s.name)]
    nothing_to_ask = not missing_required and not askable_optional

    # --- Determine the intended level (ignoring the clarify quota, which is
    # applied at ask-commit time via increment_clarify_round). ---
    if candidate_count <= LOW_CANDIDATE_THRESHOLD or nothing_to_ask:
        intended: Literal["cao", "vua", "thap"] = "thap"
    elif missing_required or candidate_count > HIGH_CANDIDATE_THRESHOLD:
        intended = "cao"
    else:  # all required filled, 6 <= candidate_count <= 20, something askable
        intended = "vua"

    if intended == "thap":
        return _proceed(profile, missing_required)

    # --- We intend to ask (Cao or Vừa): choose the slot batch. ---
    ordered_optional = _optional_by_priority(askable_optional)
    if intended == "cao":
        selected = (missing_required + ordered_optional)[:MAX_ASK_BATCH]
    else:  # vua -> a single, highest-priority optional
        selected = ordered_optional[:1]

    # Commit consumes one clarify round; if the quota is already exhausted we
    # downgrade to proceed (with assumptions for any missing required slot)
    # rather than asking beyond the cap.
    if not profile.increment_clarify_round():
        return _proceed(profile, missing_required)

    profile.mark_asked(*(slot.name for slot in selected))
    return PolicyDecision(
        level=intended,
        action="ask",
        slots_to_ask=selected,
        question_reason=_question_reason(selected),
        proceeded_with_assumptions=[],
    )
