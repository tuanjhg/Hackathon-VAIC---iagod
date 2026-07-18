"""Policy-FAQ grounded answer generation tests (src.pipeline.policy_answer)."""

import asyncio
from typing import Any

from src.pipeline.policy_answer import generate_policy_answer
from src.rag.models import PolicyChunk, SearchResult


class FakeRouter:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls = 0
        self.last_messages: list[dict[str, Any]] | None = None

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.last_messages = messages
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


def _result(title: str, heading: str, content: str, score: float) -> SearchResult:
    chunk = PolicyChunk(
        id=f"{title}-{heading}",
        source_path=f"data/policy/{title}.md",
        document_checksum="x",
        title=title,
        heading=heading,
        content=content,
        chunk_index=0,
        line_start=1,
        line_end=5,
    )
    return SearchResult(chunk=chunk, score=score)


def test_no_results_returns_honest_no_info_without_calling_llm() -> None:
    router = FakeRouter("(should not be called)")
    answer = asyncio.run(generate_policy_answer(router, "trả góp thế nào?", []))

    assert answer.grounded is False
    assert answer.sources == []
    assert "chưa có" in answer.text.lower()
    assert router.calls == 0  # honest no-data path never invokes the LLM


def test_grounded_answer_uses_excerpts_and_returns_sources() -> None:
    router = FakeRouter("Dạ trả góp 0% áp dụng cho đơn từ 3 triệu ạ.")
    results = [
        _result("chinh_sach_tra_gop", "Trả góp 0%", "Áp dụng cho đơn hàng từ 3.000.000đ.", 0.9),
        _result("chinh_sach_giao_hang", "Giao lắp", "Miễn phí nội thành.", 0.4),
    ]
    answer = asyncio.run(generate_policy_answer(router, "trả góp cần gì?", results))

    assert answer.grounded is True
    assert router.calls == 1
    assert answer.text == "Dạ trả góp 0% áp dụng cho đơn từ 3 triệu ạ."
    assert [s.title for s in answer.sources] == ["chinh_sach_tra_gop", "chinh_sach_giao_hang"]
    # The LLM was actually given the excerpt content to ground on.
    assert router.last_messages is not None
    assert "3.000.000" in router.last_messages[-1]["content"]


def test_grounded_answer_caps_number_of_excerpts() -> None:
    router = FakeRouter("ok")
    results = [_result(f"doc{i}", f"h{i}", f"content {i}", 0.9 - i * 0.1) for i in range(6)]
    answer = asyncio.run(generate_policy_answer(router, "hỏi", results, max_chunks=3))

    assert len(answer.sources) == 3  # capped to max_chunks
