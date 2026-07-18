import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from src.rag.embeddings import HashingEmbedding
from src.rag.markdown import MarkdownChunker
from src.rag.pgvector_store import PgVectorStore
from src.rag.pipeline import PolicyIndexPipeline

DEFAULT_DATABASE_URL = "postgresql://needwise:needwise@localhost:5432/needwise"

load_dotenv()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and inspect the policy vector database")
    parser.add_argument(
        "--database-url",
        default=os.getenv("POLICY_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)),
    )
    parser.add_argument("--schema", default=os.getenv("POLICY_VECTOR_SCHEMA", "policy_rag"))
    parser.add_argument("--dimension", type=int, default=384)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Synchronize Markdown policies into the index")
    build.add_argument("--source", type=Path, default=Path("data/policy"))
    build.add_argument("--chunk-size", type=int, default=1200)
    build.add_argument("--overlap", type=int, default=180)
    build.add_argument("--force", action="store_true", help="Delete and fully rebuild the database")

    search = subparsers.add_parser("search", help="Run a semantic/lexical similarity search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    subparsers.add_parser("stats", help="Print index statistics")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args()
    embedding = HashingEmbedding(args.dimension)
    store = PgVectorStore(
        args.database_url,
        embedding.dimension,
        embedding.name,
        schema=args.schema,
        force_reset=args.command == "build" and args.force,
    )
    pipeline = PolicyIndexPipeline(store, embedding)

    if args.command == "build":
        pipeline.chunker = MarkdownChunker(args.chunk_size, args.overlap)
        print(json.dumps(asdict(pipeline.build(args.source)), ensure_ascii=False, indent=2))
    elif args.command == "search":
        results = [
            {
                "score": round(result.score, 6),
                "source_path": result.chunk.source_path,
                "title": result.chunk.title,
                "heading": result.chunk.heading,
                "lines": [result.chunk.line_start, result.chunk.line_end],
                "content": result.chunk.content,
            }
            for result in pipeline.search(args.query, args.limit)
        ]
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
