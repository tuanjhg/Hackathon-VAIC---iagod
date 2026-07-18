"""Need Profile — per-session conversation state for the advisory pipeline.

Implements the "Need Profile" schema (the "bộ nhớ nhu cầu" that drives every
dialogue-policy branch) and its mutation rules, per
`docs/research/dmx-ai-workflow-v1.md` §2 "Trạng thái hội thoại" and ADR C7 of
`docs/research/dmx-tech-decisions.md`.

This module is a self-contained building block: it deliberately has no
dependency on the pipeline stages S1–S8 (added by separate work), on FastAPI,
or on persistence. Mutation is expressed as methods on the Pydantic model so
that the business invariants (clarify-round cap, never re-ask, category-change
reset) live next to the state they protect.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

MAX_CLARIFY_ROUNDS = 2
"""Hard limit on clarify rounds per conversation (workflow doc §2 and §3:
"tối đa 2 lượt hỏi/hội thoại"). ``clarify_rounds`` must never exceed this."""

DEFAULT_PRESERVED_SLOTS: tuple[str, ...] = ("ngan_sach_max",)
"""Slots that survive a category change ("giữ ngân sách"). Budget-like by
default; callers pass ``preserve_slots`` to override for categories whose
budget slot is named differently."""


class NeedProfile(BaseModel):
    """Conversation-state snapshot for one session.

    Shape mirrors the JSON example in the workflow doc §2. Slot values are
    intentionally loosely typed (``Any``) because the slot schema is
    category-specific and compiled/authored elsewhere; a slot may hold an int
    (budget), float (area), str (room type), list[str] (priorities) or ``None``
    when known-but-unfilled.
    """

    category: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict)
    asked_slots: list[str] = Field(default_factory=list)
    clarify_rounds: int = 0
    assumptions: list[str] = Field(default_factory=list)

    def merge_slots(self, new_slots: dict[str, Any], *, overwrite: bool = False) -> None:
        """Merge newly-extracted slots in (S2 → Need Profile).

        A slot that already holds a non-null value is kept, so re-extraction of
        the same turn never clobbers earlier facts. Pass ``overwrite=True`` to
        force replacement (e.g. the customer corrects a value).
        """
        for key, value in new_slots.items():
            if overwrite or self.slots.get(key) is None:
                self.slots[key] = value

    def mark_asked(self, *slot_names: str) -> None:
        """Record slots the assistant has asked about, de-duplicated and in
        first-seen order. Feeds the "never re-ask" rule via :meth:`should_ask`.
        """
        for name in slot_names:
            if name not in self.asked_slots:
                self.asked_slots.append(name)

    def should_ask(self, slot_name: str) -> bool:
        """Whether a slot may be asked: only if it has not been asked already
        and is not already filled ("không hỏi slot đã có/đã hỏi").
        """
        if slot_name in self.asked_slots:
            return False
        return self.slots.get(slot_name) is None

    def increment_clarify_round(self) -> bool:
        """Consume one clarify round, enforcing the hard cap.

        Returns ``True`` if a round was consumed, ``False`` if the cap is
        already reached — making it impossible to silently exceed
        :data:`MAX_CLARIFY_ROUNDS`.
        """
        if self.clarify_rounds >= MAX_CLARIFY_ROUNDS:
            return False
        self.clarify_rounds += 1
        return True

    def change_category(
        self, new_category: str, *, preserve_slots: Iterable[str] | None = None
    ) -> None:
        """Handle the customer switching product category mid-conversation.

        Resets category-specific slots, asked-slots and assumptions, while
        preserving budget-like slots ("reset slot ngành cũ, giữ ngân sách").
        A switch to the same category is a no-op so restating intent never
        wipes gathered facts.

        ``clarify_rounds`` is intentionally *not* reset: the 2-round quota is
        per-conversation, and a category switch must not re-open it. The light
        budget confirmation the doc suggests ("Vẫn tầm 20 triệu như lúc nãy
        ạ?") is a separate mechanism, not a clarify round against a missing
        slot.
        """
        if new_category == self.category:
            return
        preserved = set(DEFAULT_PRESERVED_SLOTS if preserve_slots is None else preserve_slots)
        self.slots = {key: value for key, value in self.slots.items() if key in preserved}
        self.asked_slots = [name for name in self.asked_slots if name in preserved]
        self.assumptions = []
        self.category = new_category

    def add_assumption(self, assumption: str) -> None:
        """Record a stated default assumption used when the clarify quota is
        exhausted but required slots are still missing ("đề xuất với giả định
        mặc định nêu rõ"), so the caller can proceed instead of blocking.
        """
        self.assumptions.append(assumption)
