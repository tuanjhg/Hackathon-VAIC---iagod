"""Tier 2 — LLM-as-judge, reference-based, one call per conversation.

Compares the bot's replayed transcript against the golden transcript and scores
four 1–5 dimensions with a short rationale. Conversation-level (not per-turn) to
keep the call count at one per conversation. The judge uses the same
``LLMRouter`` as the pipeline; output is parsed tolerantly because the provider
does not strictly enforce ``response_format`` (docs §6.9).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.eval.golden import GoldenConversation
from src.eval.replay import ReplayedConversation

_MAX_TURNS = 12
_MAX_CHARS = 320

_DIMENSIONS = ("helpfulness", "grounding", "scope_handling", "overall")

_SYSTEM_PROMPT = (
    "Bạn là giám khảo đánh giá trợ lý tư vấn điện máy tiếng Việt. Bạn được cho "
    "một hội thoại MẪU (trợ lý tốt) và câu trả lời của trợ lý ĐANG KIỂM THỬ cho "
    "cùng các câu hỏi của khách. Chấm trợ lý đang kiểm thử theo thang 1–5:\n"
    "- helpfulness: có dẫn khách tới quyết định tốt như mẫu không.\n"
    "- grounding: có bám dữ liệu, không bịa số/sản phẩm không.\n"
    "- scope_handling: có tư vấn khi làm được và từ chối/chuyển hướng lịch sự "
    "khi ngoài phạm vi (ngành không có trong catalog, tra cứu đơn hàng...) không.\n"
    "- overall: đánh giá tổng thể.\n"
    "CHỈ trả về JSON: "
    '{"helpfulness":int,"grounding":int,"scope_handling":int,"overall":int,"rationale":"..."}'
)


@dataclass
class JudgeResult:
    conversation_id: str
    scores: dict[str, int]
    rationale: str
    raw: str


def _golden_pairs(conversation: GoldenConversation) -> list[tuple[str, str]]:
    """(user_turn, following golden assistant reply) pairs, in order."""
    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for message in conversation.messages:
        if message.role == "user":
            pending_user = message.content
        elif message.role == "assistant" and pending_user is not None:
            pairs.append((pending_user, message.content))
            pending_user = None
    return pairs


def _bot_reply(replayed: ReplayedConversation, index: int) -> str:
    if index >= len(replayed.turns):
        return "[không có phản hồi]"
    turn = replayed.turns[index]
    if turn.error is not None:
        return f"[lỗi pipeline: {turn.kind}]"
    assert turn.result is not None
    return f"({turn.result.kind}) {turn.result.message}"


def _clip(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= _MAX_CHARS else text[:_MAX_CHARS] + "…"


def build_judge_messages(replayed: ReplayedConversation) -> list[dict[str, str]]:
    pairs = _golden_pairs(replayed.conversation)[:_MAX_TURNS]
    blocks: list[str] = []
    for i, (user_text, golden_reply) in enumerate(pairs):
        blocks.append(
            f"[Lượt {i + 1}]\n"
            f"Khách: {_clip(user_text)}\n"
            f"Trợ lý MẪU: {_clip(golden_reply)}\n"
            f"Trợ lý KIỂM THỬ: {_clip(_bot_reply(replayed, i))}"
        )
    user_content = "\n\n".join(blocks) if blocks else "(hội thoại rỗng)"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _parse_scores(content: str) -> tuple[dict[str, int], str]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    data: dict[str, Any] = json.loads(match.group(0)) if match else {}
    scores: dict[str, int] = {}
    for dim in _DIMENSIONS:
        value = data.get(dim)
        if isinstance(value, int | float) and not isinstance(value, bool):
            scores[dim] = max(1, min(5, int(round(value))))
    return scores, str(data.get("rationale", ""))


async def judge_conversation(replayed: ReplayedConversation, *, router: Any) -> JudgeResult:
    messages = build_judge_messages(replayed)
    response = await router.complete(messages, temperature=0)
    content = response["choices"][0]["message"]["content"]
    try:
        scores, rationale = _parse_scores(content)
    except (json.JSONDecodeError, ValueError, TypeError):
        scores, rationale = {}, ""
    return JudgeResult(
        conversation_id=replayed.conversation.id,
        scores=scores,
        rationale=rationale,
        raw=content,
    )
