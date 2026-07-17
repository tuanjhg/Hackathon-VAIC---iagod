from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.product import ProductRead


class ChatContext(BaseModel):
    budget_max: int | None = None
    room_area_m2: float | None = None
    priority: str | None = None


class ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    context: ChatContext = Field(default_factory=ChatContext)


class Recommendation(BaseModel):
    product: ProductRead
    label: str
    match_score: int
    reason: str
    strengths: list[str]
    trade_off: str


class ChatResponse(BaseModel):
    response_type: Literal["follow_up", "recommendations"]
    message: str
    quick_replies: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    context: ChatContext


class DemoScenario(BaseModel):
    title: str
    message: str

