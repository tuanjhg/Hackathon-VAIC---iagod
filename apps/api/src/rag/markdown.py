import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from src.rag.models import PolicyChunk, PolicyDocument

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def load_markdown_documents(root: Path) -> list[PolicyDocument]:
    """Load all Markdown files below root in deterministic path order."""
    if not root.exists():
        raise FileNotFoundError(f"Policy directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Policy path is not a directory: {root}")

    documents: list[PolicyDocument] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
        content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if not content.strip():
            continue
        relative_path = path.relative_to(root).as_posix()
        title = _document_title(content, path.stem)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        documents.append(PolicyDocument(relative_path, title, content, checksum))
    return documents


def _document_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            return match.group(2).strip()
    return fallback.replace("_", " ").replace("-", " ").strip()


class MarkdownChunker:
    """Split Markdown on section boundaries using overlapping character windows."""

    def __init__(self, max_chars: int = 1200, overlap_chars: int = 180) -> None:
        if max_chars < 200:
            raise ValueError("max_chars must be at least 200")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be between 0 and max_chars - 1")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(self, document: PolicyDocument) -> list[PolicyChunk]:
        chunks: list[PolicyChunk] = []
        for heading, start_line, text in self._sections(document.content):
            for line_start, line_end, content in self._windows(text, start_line):
                index = len(chunks)
                digest_input = (
                    f"{document.source_path}\0{document.checksum}\0{index}\0{content}"
                ).encode()
                chunks.append(
                    PolicyChunk(
                        id=hashlib.sha256(digest_input).hexdigest(),
                        source_path=document.source_path,
                        document_checksum=document.checksum,
                        title=document.title,
                        heading=heading,
                        content=content,
                        chunk_index=index,
                        line_start=line_start,
                        line_end=line_end,
                    )
                )
        return chunks

    @staticmethod
    def _sections(content: str) -> Iterable[tuple[str | None, int, str]]:
        lines = content.splitlines()
        heading_stack: list[str] = []
        section_lines: list[str] = []
        section_start = 1
        current_heading: str | None = None

        def emit() -> tuple[str | None, int, str] | None:
            text = "\n".join(section_lines).strip()
            return (current_heading, section_start, text) if text else None

        for number, line in enumerate(lines, start=1):
            match = _HEADING.match(line.strip())
            if not match:
                section_lines.append(line)
                continue
            section = emit()
            if section:
                yield section
            level = len(match.group(1))
            heading_stack[level - 1 :] = [match.group(2).strip()]
            current_heading = " > ".join(heading_stack)
            section_lines = []
            section_start = number + 1
        section = emit()
        if section:
            yield section

    def _windows(self, text: str, base_line: int) -> Iterable[tuple[int, int, str]]:
        start = 0
        text_length = len(text)
        while start < text_length:
            hard_end = min(start + self.max_chars, text_length)
            end = hard_end
            if hard_end < text_length:
                candidates = [text.rfind("\n\n", start, hard_end), text.rfind("\n", start, hard_end), text.rfind(" ", start, hard_end)]
                boundary = max(candidates)
                if boundary > start + self.max_chars // 2:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                prefix = text[:start]
                line_start = base_line + prefix.count("\n")
                line_end = line_start + chunk_text.count("\n")
                yield line_start, line_end, chunk_text
            if end >= text_length:
                break
            next_start = max(end - self.overlap_chars, start + 1)
            while next_start < end and not text[next_start - 1].isspace():
                next_start += 1
            start = next_start
