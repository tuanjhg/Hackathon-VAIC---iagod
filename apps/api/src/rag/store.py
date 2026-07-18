from collections.abc import Sequence
from typing import Protocol

from src.rag.models import PolicyChunk, SearchResult


class VectorStore(Protocol):
    dimension: int
    embedding_model: str

    def checksums(self) -> dict[str, str]: ...

    def replace_document(
        self,
        source_path: str,
        title: str,
        checksum: str,
        chunks: Sequence[PolicyChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None: ...

    def remove_documents_except(self, source_paths: set[str]) -> int: ...

    def search(self, query_embedding: Sequence[float], limit: int = 5) -> list[SearchResult]: ...

    def stats(self) -> dict[str, int | str]: ...
