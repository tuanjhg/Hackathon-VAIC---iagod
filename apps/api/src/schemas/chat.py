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
GuardrailStatus = Literal[
    "verified",
    "corrected",
    "grounded_fallback",
    "limited",
    "not_applicable",
    "unavailable",
]
ActionKind = Literal["quick_reply", "category", "prompt", "retry", "link"]


class SelectedAction(BaseModel):
    """A UI action selected by the customer.

    ``slot_name`` + ``value`` are validated again against the active server-side
    SlotProfile before they can mutate the Need Profile; the browser is never a
    trusted source of slot values.
    """

    id: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=120)
    slot_name: str | None = Field(default=None, max_length=80)


class ResponseAction(BaseModel):
    id: str
    kind: ActionKind
    label: str
    value: str
    slot_name: str | None = None
    url: str | None = None


class GuardrailMeta(BaseModel):
    """Customer-safe guardrail state; internal stage names stay in audit/eval."""

    status: GuardrailStatus
    label: str
    source_count: int = 0
    corrected_claims: int = 0
    omitted_claims: int = 0
    missing_data_count: int = 0
    notices: list[str] = Field(default_factory=list)


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
    selected_action: SelectedAction | None = None


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
    actions: list[ResponseAction] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    cards: list[AdvisorCard] = Field(default_factory=list)
    anti_pick: AdvisorAntiPick | None = None
    source_panel: list[SourceEntry] = Field(default_factory=list)
    verifier_flags: list[VerifierFlag] = Field(default_factory=list)
    guardrail: GuardrailMeta = Field(
        default_factory=lambda: GuardrailMeta(
            status="not_applicable", label="Không áp dụng đối chiếu dữ liệu"
        )
    )
    context: ChatContext


class DemoScenario(BaseModel):
    title: str
    message: str
