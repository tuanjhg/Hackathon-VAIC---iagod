#!/usr/bin/env python3
"""Benchmark Gate 3 -- embedding latency, CPU vs GPU-share.

Quyết định treo (dmx-tech-decisions.md, bảng cuối #3):
    Embedding CPU đủ nhanh (<30ms/query)? -> quyết định B3 (CPU hay
    GPU-share cho AITeamVN/Vietnamese_Embedding chạy in-process).

Needs `sentence-transformers` (NOT an apps/api dependency -- deliberately
kept out of the FastAPI image; heavy ML lib only needed for this one-off
benchmark + eventually the S4 rerank step). Install first:

    pip install -r scripts/bench/requirements-bench.txt

This downloads the AITeamVN/Vietnamese_Embedding model on first run
(network required) -- cannot be executed in this sandbox. Run it during
the Phase 0 GPU window (master plan Sec 5b, W1) once, and again with
--device cuda if testing GPU-share.

Usage:
    python3 scripts/bench/gate3_embedding_latency.py [--device cpu|cuda] [--n 100]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import gate_verdict, summarize  # noqa: E402

THRESHOLD_MS = 30
MODEL_NAME = "AITeamVN/Vietnamese_Embedding"

# Representative single-query soft-preference searches (S4 rerank use case --
# NOT hard-filter fields, those are SQL. See ADR B4: semantic search only for
# "sở thích mềm diễn đạt bằng lời").
SAMPLE_QUERIES = [
    "máy lạnh chạy êm cho phòng ngủ",
    "tủ lạnh sang trọng để trong bếp mở",
    "máy giặt cửa trước tiết kiệm nước",
    "màn hình chơi game tần số quét cao",
    "laptop mỏng nhẹ mang đi làm",
    "tai nghe chống ồn tốt cho văn phòng",
    "máy lọc nước công nghệ RO",
    "bếp từ đôi an toàn cho gia đình có trẻ nhỏ",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--n", type=int, default=100, help="số query mẫu (mặc định 100)")
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "Thiếu sentence-transformers. Cài trước:\n"
            "  pip install -r scripts/bench/requirements-bench.txt",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Đang tải model {MODEL_NAME} lên {args.device} (cần mạng, lần đầu chậm)...")
    model = SentenceTransformer(MODEL_NAME, device=args.device)

    # Warm-up (loading/compiling overhead shouldn't count toward per-query latency)
    model.encode(SAMPLE_QUERIES[0])

    latencies: list[float] = []
    for i in range(args.n):
        query = SAMPLE_QUERIES[i % len(SAMPLE_QUERIES)]
        start = time.perf_counter()
        model.encode(query)  # batch size 1 -- matches real runtime pattern (1 câu/lượt)
        latencies.append(time.perf_counter() - start)

    stats = summarize(latencies)
    passed = stats.p95_ms < THRESHOLD_MS

    print(f"Gate 3 -- embedding latency trên {args.device} (target p95 <{THRESHOLD_MS}ms, n={args.n})")
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    print(gate_verdict(passed))

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    out = results_dir / f"gate3_{args.device}.json"
    out.write_text(
        json.dumps({"device": args.device, "passed": passed, **stats.as_dict()}, ensure_ascii=False, indent=2)
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
