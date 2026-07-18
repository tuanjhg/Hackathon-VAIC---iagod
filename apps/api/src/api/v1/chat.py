"""Chat endpoint — S1–S8 advisory pipeline (default) or legacy mock, JSON or SSE.

Contract (§6.10): the path stays ``POST /api/v1/chat/messages``. Clients that
send ``Accept: text/event-stream`` get an SSE stream — ``delta`` events carry
the reply sentence-by-sentence (already S7-verified: sentences are only
flushed post-verification, per guardrail §4.5), then one ``final`` event
carries the full :class:`ChatResponse` JSON. Plain clients get the JSON body
unchanged, so the legacy FE keeps working during the transition.

``CHAT_PIPELINE=mock`` in the environment switches back to the rule-based
:class:`MockChatService` (no LLM needed) — the demo-safe escape hatch.
"""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import get_db
from src.repositories.product_repository import ProductRepository
from src.schemas.chat import ChatMessageRequest, ChatResponse, DemoScenario
from src.services.advisor_chat_service import AdvisorChatService, delete_advisor_session
from src.services.mock_chat_service import MockChatService
from src.services.product_service import ProductService
from src.verifier import sentence_spans

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse_events(response: ChatResponse) -> Iterator[str]:
    """Sentence-buffered deltas, then the full payload as the final event."""
    for start, end in sentence_spans(response.message):
        sentence = response.message[start:end].strip()
        if sentence:
            payload = json.dumps({"type": "delta", "text": sentence}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
    final = json.dumps(
        {"type": "final", "response": response.model_dump(mode="json")}, ensure_ascii=False
    )
    yield f"data: {final}\n\n"


@router.post("/messages", response_model=None)
async def send_message(
    request: ChatMessageRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> ChatResponse | StreamingResponse:
    if settings.chat_pipeline == "mock":
        response = MockChatService(ProductService(ProductRepository(db))).reply(request)
    else:
        response = await AdvisorChatService(db).reply(request)

    if "text/event-stream" in http_request.headers.get("accept", ""):
        return StreamingResponse(_sse_events(response), media_type="text/event-stream")
    return response


@router.get("/demo-scenarios", response_model=list[DemoScenario])
def demo_scenarios() -> list[DemoScenario]:
    return [
        DemoScenario(title="Phòng ngủ 18m²", message="Tư vấn máy lạnh cho phòng 18m2"),
        DemoScenario(title="Phòng khách 30m²", message="Tư vấn máy lạnh cho phòng 30m2"),
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str) -> Response:
    """Forget the in-memory Need Profile associated with this chat session."""
    delete_advisor_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
