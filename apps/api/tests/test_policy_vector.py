from pathlib import Path

import pytest

from src.rag.embeddings import HashingEmbedding
from src.rag.markdown import MarkdownChunker, load_markdown_documents
from src.rag.memory_store import MemoryVectorStore
from src.rag.pgvector_store import normalize_psycopg_url, vector_literal
from src.rag.pipeline import PolicyIndexPipeline


def make_pipeline(tmp_path: Path, dimension: int = 128) -> PolicyIndexPipeline:
    embedding = HashingEmbedding(dimension)
    store = MemoryVectorStore(dimension, embedding.name)
    return PolicyIndexPipeline(store, embedding, MarkdownChunker(220, 40))


def test_loader_and_chunker_preserve_markdown_metadata(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "returns.md").write_text(
        "# Chính sách đổi trả\n\n## Điều kiện\n\n" + "Sản phẩm lỗi được đổi mới. " * 20,
        encoding="utf-8",
    )
    document = load_markdown_documents(policy_dir)[0]
    chunks = MarkdownChunker(220, 40).split(document)
    assert document.title == "Chính sách đổi trả"
    assert len(chunks) >= 2
    assert all(chunk.source_path == "returns.md" for chunk in chunks)
    assert all(chunk.heading == "Chính sách đổi trả > Điều kiện" for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.line_start <= chunk.line_end for chunk in chunks)


def test_build_is_idempotent_and_search_returns_relevant_policy(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "warranty.md").write_text(
        "# Bảo hành\nSản phẩm lỗi kỹ thuật được bảo hành trong mười hai tháng.", encoding="utf-8"
    )
    (policy_dir / "delivery.md").write_text(
        "# Giao hàng\nĐơn hàng được giao miễn phí và hỗ trợ lắp đặt tại nhà.", encoding="utf-8"
    )
    pipeline = make_pipeline(tmp_path)
    first = pipeline.build(policy_dir)
    second = pipeline.build(policy_dir)
    results = pipeline.search("thời gian bảo hành lỗi kỹ thuật", limit=2)
    assert first.indexed_documents == 2
    assert first.indexed_chunks == 2
    assert second.indexed_documents == 0
    assert second.skipped_documents == 2
    assert pipeline.store.stats()["documents"] == 2
    assert results[0].chunk.source_path == "warranty.md"
    assert results[0].score > results[1].score


def test_build_replaces_changed_document_and_removes_deleted_source(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    changed = policy_dir / "changed.md"
    removed = policy_dir / "removed.md"
    changed.write_text("Nội dung ban đầu về bảo hành.", encoding="utf-8")
    removed.write_text("Chính sách sẽ bị xóa.", encoding="utf-8")
    pipeline = make_pipeline(tmp_path)
    pipeline.build(policy_dir)
    changed.write_text("Nội dung mới về giao hàng và lắp đặt.", encoding="utf-8")
    removed.unlink()
    report = pipeline.build(policy_dir)
    assert report.indexed_documents == 1
    assert report.removed_documents == 1
    assert pipeline.store.stats()["documents"] == 1
    result = pipeline.search("giao hàng lắp đặt", limit=1)[0]
    assert result.chunk.source_path == "changed.md"
    assert "Nội dung mới" in result.chunk.content


def test_pgvector_helpers_validate_dimension_and_sqlalchemy_url() -> None:
    assert normalize_psycopg_url("postgresql+psycopg://user:pass@db/app") == (
        "postgresql://user:pass@db/app"
    )
    assert vector_literal([0.25, -0.5], 2) == "[0.25,-0.5]"
    with pytest.raises(ValueError, match="Expected embedding dimension"):
        vector_literal([0.25], 2)


def test_empty_query_is_rejected(tmp_path: Path) -> None:
    pipeline = make_pipeline(tmp_path)
    with pytest.raises(ValueError, match="must not be empty"):
        pipeline.search("  ")
