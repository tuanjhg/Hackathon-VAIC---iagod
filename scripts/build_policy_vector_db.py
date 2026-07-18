"""Build or synchronize the policy vector database."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env")
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api"))

from src.rag.embeddings import HashingEmbedding  # noqa: E402
from src.rag.markdown import MarkdownChunker  # noqa: E402
from src.rag.pipeline import PolicyIndexPipeline  # noqa: E402
from src.rag.pgvector_store import PgVectorStore  # noqa: E402

DEFAULT_DATABASE_URL = "postgresql://needwise:needwise@localhost:5432/needwise"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPOSITORY_ROOT / "data" / "policy")
    parser.add_argument(
        "--database-url",
        default=os.getenv("POLICY_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)),
    )
    parser.add_argument("--schema", default=os.getenv("POLICY_VECTOR_SCHEMA", "policy_rag"))
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--overlap", type=int, default=180)
    parser.add_argument("--dimension", type=int, default=384)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    embedding = HashingEmbedding(args.dimension)
    pipeline = PolicyIndexPipeline(
        PgVectorStore(
            args.database_url,
            embedding.dimension,
            embedding.name,
            schema=args.schema,
            force_reset=args.force,
        ),
        embedding,
        MarkdownChunker(args.chunk_size, args.overlap),
    )
    print(json.dumps(asdict(pipeline.build(args.source)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
