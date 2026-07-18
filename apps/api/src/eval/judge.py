"""Tier 2 — reference-based LLM judge plus the business binary rubric.

The judge sees the complete user-visible response (prose, structured cards,
anti-pick and provenance), not only the LLM prose. It keeps the legacy four
1–5 dimensions for trend continuity and adds the explicit yes/no criteria from
``docs/research/dmx-data-eval-roi-plan.md`` §B3 and the local-tone extension.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.eval.golden import GoldenConversation
from src.eval.replay import ReplayedConversation
from src.services.advisor_chat_service import _FALLBACK_MESSAGE, _to_chat_response

_MAX_TURNS = 12
_MAX_CHARS = 1600

_DIMENSIONS = ("helpfulness", "grounding", "scope_handling", "overall")
_BUSINESS_CRITERIA = (
    "needs_summary",
    "plain_vietnamese",
    "product_advantage_and_tradeoff",
    "anti_pick_with_reason",
    "non_pushy_tone",
    "clarification_has_reason",
    "consistent_vietnamese_pronouns",
)
_RECOMMENDATION_CRITERIA = (
    "needs_summary",
    "product_advantage_and_tradeoff",
    "anti_pick_with_reason",
)

_SYSTEM_PROMPT = (
    "Bạn là giám khảo đánh giá trợ lý tư vấn điện máy tiếng Việt. Bạn được cho "
    "một hội thoại MẪU (trợ lý tốt) và câu trả lời của trợ lý ĐANG KIỂM THỬ cho "
    "cùng các câu hỏi của khách. Chấm trợ lý đang kiểm thử theo thang 1–5:\n"
    "- helpfulness: có dẫn khách tới quyết định tốt như mẫu không.\n"
    "- grounding: có bám dữ liệu, không bịa số/sản phẩm không.\n"
    "- scope_handling: có tư vấn khi làm được và từ chối/chuyển hướng lịch sự "
    "khi ngoài phạm vi (ngành không có trong catalog, tra cứu đơn hàng...) không.\n"
    "- overall: đánh giá tổng thể.\n\n"
    "Đồng thời chấm các tiêu chí nghiệp vụ bằng true/false; dùng null nếu tiêu chí "
    "thực sự không áp dụng cho hội thoại này:\n"
    "- needs_summary: trước khi đề xuất có tóm tắt nhu cầu khách.\n"
    "- plain_vietnamese: tiếng Việt bình dân, thuật ngữ được giải thích.\n"
    "- product_advantage_and_tradeoff: mỗi sản phẩm đề xuất có cả ưu điểm và đánh đổi.\n"
    "- anti_pick_with_reason: có sản phẩm không nên chọn và lý do rõ.\n"
    "- non_pushy_tone: gần gũi, không ép mua, không phóng đại.\n"
    "- clarification_has_reason: nếu hỏi làm rõ, có nói vì sao cần hỏi.\n"
    "- consistent_vietnamese_pronouns: xưng em, gọi khách anh/chị nhất quán.\n"
    "CHỈ trả về JSON: "
    '{"helpfulness":int,"grounding":int,"scope_handling":int,"overall":int,'
    '"business_checks":{"needs_summary":bool|null,"plain_vietnamese":bool|null,'
    '"product_advantage_and_tradeoff":bool|null,"anti_pick_with_reason":bool|null,'
    '"non_pushy_tone":bool|null,"clarification_has_reason":bool|null,'
    '"consistent_vietnamese_pronouns":bool|null},"rationale":"..."}'
)


@dataclass
class JudgeResult:
    conversation_id: str
    scores: dict[str, int]
    business_checks: dict[str, bool | None]
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
        # Replay calls the framework-free orchestrator directly, but production
        # catches this exception and shows a polite fallback. Judge the actual
        # user-visible contract while Tier 1 still records ``kind=error``.
        return _FALLBACK_MESSAGE
    assert turn.result is not None
    response = _to_chat_response(turn.result)
    parts = [response.message]
    if response.cards:
        rendered_cards = []
        for card in response.cards:
            strengths = "; ".join(card.strengths) or "chưa có ưu điểm hiển thị"
            rendered_cards.append(
                f"{card.name} | ưu: {strengths} | đánh đổi: {card.trade_off}"
            )
        parts.append("THẺ SẢN PHẨM: " + " || ".join(rendered_cards))
    if response.anti_pick is not None:
        parts.append(
            "KHÔNG NÊN CHỌN: "
            f"{response.anti_pick.name} | lý do: {response.anti_pick.reason or 'chưa nêu'}"
        )
    if response.source_panel:
        parts.append(f"NGUỒN DỮ LIỆU: {len(response.source_panel)} mục")
    return "\n".join(parts)


def _clip(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= _MAX_CHARS else text[:_MAX_CHARS] + "…"


def build_judge_messages(replayed: ReplayedConversation) -> list[dict[str, str]]:
    # Compare only turns that were actually replayed. The runner deliberately
    # caps long raw exports for predictable cloud cost/latency; showing later
    # golden turns as "không có phản hồi" would incorrectly penalize the bot.
    pairs = _golden_pairs(replayed.conversation)[: min(_MAX_TURNS, len(replayed.turns))]
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


def _parse_scores(content: str) -> tuple[dict[str, int], dict[str, bool | None], str]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    data: dict[str, Any] = json.loads(match.group(0)) if match else {}
    scores: dict[str, int] = {}
    for dim in _DIMENSIONS:
        value = data.get(dim)
        if isinstance(value, int | float) and not isinstance(value, bool):
            scores[dim] = max(1, min(5, int(round(value))))
    raw_checks = data.get("business_checks")
    checks: dict[str, bool | None] = {}
    if isinstance(raw_checks, dict):
        for criterion in _BUSINESS_CRITERIA:
            value = raw_checks.get(criterion)
            if isinstance(value, bool) or value is None:
                checks[criterion] = value
    return scores, checks, str(data.get("rationale", ""))


def _apply_applicability(
    replayed: ReplayedConversation, checks: dict[str, bool | None]
) -> dict[str, bool | None]:
    """Make conditional rubric items deterministic instead of judge-dependent."""
    normalized = dict(checks)
    kinds = {turn.kind for turn in replayed.turns}
    if "recommend" not in kinds:
        for criterion in _RECOMMENDATION_CRITERIA:
            normalized[criterion] = None
    if not kinds.intersection({"ask", "ask_category"}):
        normalized["clarification_has_reason"] = None
    return normalized


async def judge_conversation(replayed: ReplayedConversation, *, router: Any) -> JudgeResult:
    messages = build_judge_messages(replayed)
    response = await router.complete(messages, temperature=0)
    content = response["choices"][0]["message"]["content"]
    try:
        scores, business_checks, rationale = _parse_scores(content)
    except (json.JSONDecodeError, ValueError, TypeError):
        scores, business_checks, rationale = {}, {}, ""
    business_checks = _apply_applicability(replayed, business_checks)
    return JudgeResult(
        conversation_id=replayed.conversation.id,
        scores=scores,
        business_checks=business_checks,
        rationale=rationale,
        raw=content,
    )
