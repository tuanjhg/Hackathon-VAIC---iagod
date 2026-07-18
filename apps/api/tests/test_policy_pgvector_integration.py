import os
from pathlib import Path

import pytest

from src.rag.embeddings import HashingEmbedding
from src.rag.pgvector_store import PgVectorStore
from src.rag.pipeline import PolicyIndexPipeline

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("POLICY_TEST_DATABASE_URL"),
    reason="Set POLICY_TEST_DATABASE_URL to run PostgreSQL/pgvector integration tests",
)
def test_pgvector_build_idempotency_and_search(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "warranty.md").write_text(
        "# Bảo hành\nSản phẩm lỗi kỹ thuật được bảo hành mười hai tháng.", encoding="utf-8"
    )
    (policy_dir / "delivery.md").write_text(
        "# Giao hàng\nĐơn hàng được giao miễn phí và lắp đặt tại nhà.", encoding="utf-8"
    )
    embedding = HashingEmbedding(384)
    store = PgVectorStore(
        os.environ["POLICY_TEST_DATABASE_URL"],
        embedding.dimension,
        embedding.name,
        schema="policy_rag_test",
        force_reset=True,
    )
    pipeline = PolicyIndexPipeline(store, embedding)

    first = pipeline.build(policy_dir)
    second = pipeline.build(policy_dir)
    results = pipeline.search("bảo hành sản phẩm lỗi kỹ thuật", limit=2)

    assert first.indexed_documents == 2
    assert second.skipped_documents == 2
    assert store.stats()["backend"] == "postgresql+pgvector"
    assert results[0].chunk.source_path == "warranty.md"
    assert results[0].score > results[1].score
