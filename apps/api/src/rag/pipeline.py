from pathlib import Path

from src.rag.embeddings import HashingEmbedding
from src.rag.markdown import MarkdownChunker, load_markdown_documents
from src.rag.models import IndexReport, SearchResult
from src.rag.store import VectorStore


class PolicyIndexPipeline:
    def __init__(
        self,
        store: VectorStore,
        embedding: HashingEmbedding,
        chunker: MarkdownChunker | None = None,
    ) -> None:
        if store.dimension != embedding.dimension:
            raise ValueError("Store and embedding dimensions must match")
        self.store = store
        self.embedding = embedding
        self.chunker = chunker or MarkdownChunker()

    def build(self, policy_dir: Path) -> IndexReport:
        documents = load_markdown_documents(policy_dir)
        current = self.store.checksums()
        indexed_documents = 0
        skipped_documents = 0
        indexed_chunks = 0

        for document in documents:
            if current.get(document.source_path) == document.checksum:
                skipped_documents += 1
                continue
            chunks = self.chunker.split(document)
            embeddings = self.embedding.embed([chunk.content for chunk in chunks])
            self.store.replace_document(
                document.source_path, document.title, document.checksum, chunks, embeddings
            )
            indexed_documents += 1
            indexed_chunks += len(chunks)

        removed = self.store.remove_documents_except({document.source_path for document in documents})
        return IndexReport(
            discovered_documents=len(documents),
            indexed_documents=indexed_documents,
            skipped_documents=skipped_documents,
            removed_documents=removed,
            indexed_chunks=indexed_chunks,
        )

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        return self.store.search(self.embedding.embed([query])[0], limit)
