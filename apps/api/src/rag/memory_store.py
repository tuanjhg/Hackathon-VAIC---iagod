import math
from collections.abc import Sequence

from src.rag.models import PolicyChunk, SearchResult


class MemoryVectorStore:
    """Small test double implementing the vector-store contract without infrastructure."""

    def __init__(self, dimension: int, embedding_model: str) -> None:
        self.dimension = dimension
        self.embedding_model = embedding_model
        self._documents: dict[str, tuple[str, str]] = {}
        self._chunks: dict[str, tuple[PolicyChunk, list[float]]] = {}

    def checksums(self) -> dict[str, str]:
        return {path: value[0] for path, value in self._documents.items()}

    def replace_document(
        self,
        source_path: str,
        title: str,
        checksum: str,
        chunks: Sequence[PolicyChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        self._chunks = {
            key: value for key, value in self._chunks.items() if value[0].source_path != source_path
        }
        self._documents[source_path] = (checksum, title)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            if len(embedding) != self.dimension:
                raise ValueError(f"Expected embedding dimension {self.dimension}")
            self._chunks[chunk.id] = (chunk, list(embedding))

    def remove_documents_except(self, source_paths: set[str]) -> int:
        removed = set(self._documents) - source_paths
        for source_path in removed:
            del self._documents[source_path]
        self._chunks = {
            key: value
            for key, value in self._chunks.items()
            if value[0].source_path in source_paths
        }
        return len(removed)

    def search(self, query_embedding: Sequence[float], limit: int = 5) -> list[SearchResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if len(query_embedding) != self.dimension:
            raise ValueError(f"Expected embedding dimension {self.dimension}")
        query_norm = math.sqrt(sum(value * value for value in query_embedding))
        results = []
        for chunk, embedding in self._chunks.values():
            norm = math.sqrt(sum(value * value for value in embedding))
            score = 0.0 if not query_norm or not norm else sum(
                left * right for left, right in zip(query_embedding, embedding, strict=True)
            ) / (query_norm * norm)
            results.append(SearchResult(chunk, score))
        return sorted(results, key=lambda result: (-result.score, result.chunk.id))[:limit]

    def stats(self) -> dict[str, int | str]:
        return {
            "documents": len(self._documents),
            "chunks": len(self._chunks),
            "dimension": self.dimension,
            "embedding_model": self.embedding_model,
        }
