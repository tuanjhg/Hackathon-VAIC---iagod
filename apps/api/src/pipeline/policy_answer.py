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

import re
from dataclasses import dataclass
from typing import Any, Protocol

from src.pipeline.humanize import fold_ascii
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
    fallback_used: bool = False


_NUMBER_RE = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)*)(?:\s*(?P<unit>triệu|tr|nghìn|ngàn|k))?",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9_]+")
_STOPWORDS = frozenset(
    {
        "anh",
        "chi",
        "da",
        "em",
        "la",
        "va",
        "co",
        "theo",
        "duoc",
        "trong",
        "nay",
        "hien",
        "tai",
        "a",
    }
)


def _normalized_numbers(text: str) -> set[str]:
    normalized: set[str] = set()
    multipliers = {"triệu": 1_000_000, "tr": 1_000_000, "nghìn": 1_000, "ngàn": 1_000, "k": 1_000}
    for match in _NUMBER_RE.finditer(text):
        raw = match.group("number")
        unit = (match.group("unit") or "").lower()
        if unit:
            value = float(raw.replace(",", "."))
            normalized.add(str(round(value * multipliers[unit])))
        else:
            normalized.add(re.sub(r"[.,]", "", raw))
    return normalized


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _WORD_RE.findall(fold_ascii(text).replace("_", " "))
        if len(token) > 2 and token not in _STOPWORDS
    }


def _is_grounded_answer(text: str, query: str, results: list[SearchResult]) -> bool:
    """Conservative post-check for policy prose before it reaches customers.

    Every number must exist in the retrieved material/query and the substantive
    vocabulary must overlap the evidence.  A rejected paraphrase is replaced by
    a direct excerpt, preferring an occasional plain answer over a fabricated
    policy term or deadline.
    """
    evidence = query + "\n" + "\n".join(
        f"{result.chunk.title} {result.chunk.heading or ''} {result.chunk.content}"
        for result in results
    )
    if not _normalized_numbers(text) <= _normalized_numbers(evidence):
        return False
    answer_tokens = _content_tokens(text)
    if not answer_tokens:
        return False
    overlap = len(answer_tokens & _content_tokens(evidence)) / len(answer_tokens)
    return len(text) <= 1200 and overlap >= 0.35


def _direct_excerpt(result: SearchResult) -> str:
    chunk = result.chunk
    content = " ".join(chunk.content.split())
    if len(content) > 700:
        content = content[:697].rstrip() + "…"
    section = chunk.heading or chunk.title
    return f"Dạ theo mục chính sách “{section}” ({chunk.title}): {content}"


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
    text = content.strip() if isinstance(content, str) else ""
    if not _is_grounded_answer(text, query, top):
        return PolicyAnswer(
            text=_direct_excerpt(top[0]),
            sources=sources,
            grounded=True,
            fallback_used=True,
        )
    return PolicyAnswer(text=text, sources=sources, grounded=True)
