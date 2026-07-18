"""Policy-FAQ answer generation for the ``policy_faq`` intent branch.

Grounded generation, same discipline as S6: the LLM sees *only* the retrieved
policy excerpts and must answer from them, citing the source document/section —
it never invents policy. When retrieval returns nothing, we return an honest
"chưa có thông tin" message with no LLM call at all (guardrail Tầng 3).

Kept LLM-agnostic and I/O-free: the caller injects an ``LLMRouterLike`` and the
already-retrieved :class:`~src.rag.models.SearchResult` list, so this is unit
tested with fakes and no vector store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.rag.models import SearchResult

_MAX_CHUNKS = 4

_NO_INFO_MESSAGE = (
    "Dạ thông tin này em chưa có trong tài liệu chính sách hiện có ạ. "
    "Anh/chị có thể liên hệ tổng đài Điện Máy Xanh hoặc để em hỗ trợ tư vấn sản phẩm giúp mình nhé."
)

_SYSTEM_PROMPT = (
    "Bạn là trợ lý CSKH Điện Máy Xanh trả lời câu hỏi chính sách (bảo hành, đổi "
    "trả, trả góp, giao lắp, xử lý dữ liệu cá nhân) bằng tiếng Việt.\n"
    "CHỈ trả lời dựa trên các TRÍCH ĐOẠN chính sách được cung cấp bên dưới. "
    "Nếu trích đoạn không chứa câu trả lời, nói rõ là chưa có thông tin và mời "
    "khách liên hệ tổng đài — TUYỆT ĐỐI không bịa điều khoản, con số hay thời hạn.\n"
    "Trả lời ngắn gọn bằng tiếng Việt bình dân; xưng 'em', gọi khách là "
    "'anh/chị'; không dùng giọng hành chính, không markdown. Nêu mục chính sách đã dựa vào."
)


class LLMRouterLike(Protocol):
    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PolicySource:
    title: str
    heading: str | None
    source_path: str


@dataclass(frozen=True)
class PolicyAnswer:
    text: str
    sources: list[PolicySource]
    grounded: bool  # False = no relevant excerpt found (honest no-data path)


def _excerpt_block(results: list[SearchResult]) -> str:
    blocks: list[str] = []
    for i, result in enumerate(results, 1):
        chunk = result.chunk
        heading = f" — {chunk.heading}" if chunk.heading else ""
        blocks.append(f"[{i}] {chunk.title}{heading}\n{chunk.content}")
    return "\n\n".join(blocks)


async def generate_policy_answer(
    router: LLMRouterLike, query: str, results: list[SearchResult], *, max_chunks: int = _MAX_CHUNKS
) -> PolicyAnswer:
    """Answer a policy question grounded in the retrieved excerpts (or say so)."""
    top = results[:max_chunks]
    if not top:
        return PolicyAnswer(text=_NO_INFO_MESSAGE, sources=[], grounded=False)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Câu hỏi của khách: {query}\n\nTRÍCH ĐOẠN CHÍNH SÁCH:\n{_excerpt_block(top)}",
        },
    ]
    response = await router.complete(messages, temperature=0)
    content = response["choices"][0]["message"]["content"]
    sources = [
        PolicySource(title=r.chunk.title, heading=r.chunk.heading, source_path=r.chunk.source_path)
        for r in top
    ]
    return PolicyAnswer(text=content.strip(), sources=sources, grounded=True)
