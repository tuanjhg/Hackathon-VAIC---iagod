"""Replay a golden conversation's user turns through the live pipeline.

Drives :func:`src.pipeline.orchestrator.run_turn` directly (not the thin
``AdvisorChatService`` shell) so each turn yields the full :class:`TurnResult` —
its ``kind`` (ask / recommend / out_of_scope / unsupported / …), the engaged
category, the ranking and the verification — which the structural metrics and
the LLM judge both need. The retriever adapter mirrors the one the production
service builds, so the catalog path under test is identical.

A conversation is replayed by feeding only its *user* turns in order against a
single fresh :class:`NeedProfile` (mutated across turns, exactly like a real
session). The golden *assistant* turns are the reference the judge compares to,
not fed back in — divergence between what the bot says and the golden answer is
part of what we are measuring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.eval.golden import GoldenConversation
from src.pipeline.need_profile import NeedProfile
from src.pipeline.orchestrator import RetrievalResult, TurnResult, run_turn
from src.pipeline.s2_extract import S2ExtractionError
from src.pipeline.s6_generate import S6GenerationError
from src.router.client import LLMRouterError
from src.tools.catalog_search import catalog_search
from src.tools.price_promo_stock import PricePromoStockTool


@dataclass
class ReplayTurn:
    """One replayed user turn and what the bot did with it."""

    user_text: str
    result: TurnResult | None  # None when the turn raised (recorded in ``error``)
    error: str | None = None

    @property
    def kind(self) -> str:
        if self.error is not None:
            return "error"
        assert self.result is not None
        return self.result.kind


@dataclass
class ReplayedConversation:
    conversation: GoldenConversation
    turns: list[ReplayTurn]

    @property
    def category(self) -> str | None:
        """The category the bot ultimately engaged (last non-null wins)."""
        category: str | None = None
        for turn in self.turns:
            if turn.result is not None and turn.result.profile.category:
                category = turn.result.profile.category
        return category

    @property
    def recommended(self) -> bool:
        return any(t.kind == "recommend" for t in self.turns)


def _make_retriever(db: Session) -> Any:
    """Same catalog adapter the production service uses (ORM rows → candidate dicts)."""

    def retrieve(
        *, category_key: str, budget_max: int | None, slots: dict[str, Any], limit: int
    ) -> RetrievalResult:
        found = catalog_search(
            db, category_key=category_key, budget_max=budget_max, slots=slots, limit=limit
        )
        candidates = [
            {
                "sku": p.sku,
                "name": p.name,
                "specs": p.specs_json or {},
                "image_url": p.image_url,
            }
            for p in found.products
        ]
        return RetrievalResult(candidates=candidates, total_count=found.total_count)

    return retrieve


async def replay_conversation(
    conversation: GoldenConversation,
    *,
    db: Session,
    router: Any,
    facts_tool: Any | None = None,
    policy_search: Any | None = None,
) -> ReplayedConversation:
    """Feed the conversation's user turns through the pipeline, one by one."""
    profile = NeedProfile()
    retriever = _make_retriever(db)
    tool = facts_tool or PricePromoStockTool()
    turns: list[ReplayTurn] = []

    for user_text in conversation.user_turns:
        try:
            result = await run_turn(
                user_text,
                profile,
                router=router,
                retriever=retriever,
                facts_tool=tool,
                policy_search=policy_search,
            )
            turns.append(ReplayTurn(user_text=user_text, result=result))
        except (LLMRouterError, S2ExtractionError, S6GenerationError) as exc:
            turns.append(ReplayTurn(user_text=user_text, result=None, error=repr(exc)))

    return ReplayedConversation(conversation=conversation, turns=turns)
