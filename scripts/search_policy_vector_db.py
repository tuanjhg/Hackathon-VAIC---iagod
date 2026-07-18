"""Inspect retrieval results from the policy vector database."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env")
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api"))

from src.rag.embeddings import HashingEmbedding  # noqa: E402
from src.rag.pipeline import PolicyIndexPipeline  # noqa: E402
from src.rag.pgvector_store import PgVectorStore  # noqa: E402

DEFAULT_DATABASE_URL = "postgresql://needwise:needwise@localhost:5432/needwise"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument(
        "--database-url",
        default=os.getenv("POLICY_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)),
    )
    parser.add_argument("--schema", default=os.getenv("POLICY_VECTOR_SCHEMA", "policy_rag"))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dimension", type=int, default=384)
    args = parser.parse_args()
    embedding = HashingEmbedding(args.dimension)
    pipeline = PolicyIndexPipeline(
        PgVectorStore(args.database_url, embedding.dimension, embedding.name, schema=args.schema),
        embedding,
    )
    results = [
        {
            "rank": rank,
            "score": round(result.score, 6),
            "source_path": result.chunk.source_path,
            "heading": result.chunk.heading,
            "lines": [result.chunk.line_start, result.chunk.line_end],
            "content": result.chunk.content,
        }
        for rank, result in enumerate(pipeline.search(args.query, args.limit), start=1)
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
