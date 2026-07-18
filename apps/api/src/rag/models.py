from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PolicyDocument:
    source_path: str
    title: str
    content: str
    checksum: str


@dataclass(frozen=True, slots=True)
class PolicyChunk:
    id: str
    source_path: str
    document_checksum: str
    title: str
    heading: str | None
    content: str
    chunk_index: int
    line_start: int
    line_end: int


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk: PolicyChunk
    score: float


@dataclass(frozen=True, slots=True)
class IndexReport:
    discovered_documents: int
    indexed_documents: int
    skipped_documents: int
    removed_documents: int
    indexed_chunks: int
