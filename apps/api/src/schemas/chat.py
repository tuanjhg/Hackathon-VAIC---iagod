from typing import Any, Literal

from pydantic import BaseModel, Field

from src.pipeline.need_profile import NeedProfile
from src.pipeline.s8_respond import SourceEntry, VerifierFlag
from src.schemas.product import ProductRead

ChatResponseType = Literal[
    "follow_up",
    "clarification",
    "recommendations",
    "policy",
    "no_results",
    "handoff",
    "out_of_scope",
    "unsupported",
    "error",
]


class ChatContext(BaseModel):
    """Conversation context echoed between turns.

    The three legacy scalar fields keep the rule-based FE contract working;
    ``need_profile`` is the full §6.2 state used by the AI pipeline (§6.10).
    The server-side session store is authoritative — ``need_profile`` here is
    the transparency/recovery copy (e.g. after an API restart).
    """

    budget_max: int | None = None
    room_area_m2: float | None = None
    priority: str | None = None
    need_profile: NeedProfile | None = None


class ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    context: ChatContext = Field(default_factory=ChatContext)


class Recommendation(BaseModel):
    """Legacy card for the rule-based mock flow (demo products only)."""

    product: ProductRead
    label: str
    match_score: int
    reason: str
    strengths: list[str]
    trade_off: str


class AdvisorCard(BaseModel):
    """AI-pipeline product card, rendered straight from the S5 candidate JSON
    (ADR C5 — no LLM, no ``ProductRead`` fabrication for realdata rows that
    lack the demo relationships). ``trade_off`` is mandatory per guardrail
    Tầng 4 ("card nào cũng phải có trade-off").
    """

    sku: str
    product_slug: str | None = None
    name: str
    label: str
    match_score: int
    price: int | None = None
    image_url: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    reason: str
    strengths: list[str] = Field(default_factory=list)
    trade_off: str
    missing_fields: list[str] = Field(default_factory=list)


class AdvisorAntiPick(BaseModel):
    """The "không nên chọn" card (§6.10 anti_pick)."""

    sku: str
    name: str
    reason: str | None = None


class ChatResponse(BaseModel):
    response_type: ChatResponseType
    intent: str | None = None
    message: str
    quick_replies: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    cards: list[AdvisorCard] = Field(default_factory=list)
    anti_pick: AdvisorAntiPick | None = None
    source_panel: list[SourceEntry] = Field(default_factory=list)
    verifier_flags: list[VerifierFlag] = Field(default_factory=list)
    context: ChatContext


class DemoScenario(BaseModel):
    title: str
    message: str
