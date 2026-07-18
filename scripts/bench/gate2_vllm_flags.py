#!/usr/bin/env python3
"""Benchmark Gate 2 -- prefix-caching + chunked-prefill flag pair, TTFT impact.

Quyết định treo (dmx-tech-decisions.md, bảng cuối #2):
    Cặp flag prefix-caching + chunked-prefill ổn trên version vLLM đang
    dùng? -> quyết định D3 flag cuối cùng (docker-compose vllm command).

A single client script cannot toggle server-side vLLM flags -- run this
script TWICE against two separately-launched vLLM instances (or the same
instance restarted with different flags) and diff the two result files:

    # window A: vllm launched WITHOUT the flag pair
    python3 scripts/bench/gate2_vllm_flags.py --label flags-off

    # window B: vllm launched WITH --enable-prefix-caching --enable-chunked-prefill
    python3 scripts/bench/gate2_vllm_flags.py --label flags-on

    diff scripts/bench/results/gate2_flags-off.json scripts/bench/results/gate2_flags-on.json

Requires a running vLLM OpenAI-compatible endpoint (VLLM_BASE_URL). This
cannot be executed in the dev/build sandbox -- run it during the Phase 0
GPU window (master plan Sec 5b, W1). See scripts/bench/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import chat_completion_stream, summarize  # noqa: E402

# Mix of short (question, mimics S3a hỏi ngược) and longer (advisory, mimics S6)
# prompts -- TTFT under repeated similar system prompts is exactly what prefix
# caching is meant to help with.
SYSTEM_PROMPT_SHORT = "Bạn là trợ lý tư vấn điện máy, hỏi ngắn gọn 1 câu để làm rõ nhu cầu."
SYSTEM_PROMPT_LONG = (
    "Bạn là trợ lý tư vấn điện máy. Diễn đạt lại các statement sau thành lời tư vấn "
    "bình dân, gần gũi, không thêm số liệu mới, có nêu trade-off rõ ràng giữa các lựa chọn."
)

PROMPTS = [
    (SYSTEM_PROMPT_SHORT, "Khách nói: phòng 18m2, ngân sách 20 triệu. Cần hỏi thêm gì?"),
    (SYSTEM_PROMPT_SHORT, "Khách nói: tủ lạnh cho 4 người. Cần hỏi thêm gì?"),
    (
        SYSTEM_PROMPT_LONG,
        "SP1 Daikin 24000BTU 24dB giá 15tr; SP2 Panasonic 24000BTU 31dB giá 13tr. "
        "Khách ưu tiên chạy êm. Viết lời tư vấn.",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="vd: flags-on / flags-off")
    parser.add_argument("--n", type=int, default=15, help="số request mẫu (mặc định 15)")
    args = parser.parse_args()

    ttfts: list[float] = []
    errors: list[str] = []
    for i in range(args.n):
        system, user = PROMPTS[i % len(PROMPTS)]
        result = chat_completion_stream(
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
                "reasoning": {"enabled": False},  # archived script, kept consistent with gate1/4 fix
            }
        )
        if result.ok and result.ttft_s is not None:
            ttfts.append(result.ttft_s)
        else:
            errors.append(result.error or "no TTFT captured")

    stats = summarize(ttfts, errors)
    print(f"Gate 2 -- TTFT với label='{args.label}' (n={args.n})")
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    print(
        "Không có ngưỡng pass/fail cứng ở đây -- so 2 file kết quả (flags-on vs "
        "flags-off) bằng `diff`. Nếu flags-on có p95 CAO hơn hoặc có lỗi mới "
        "(bug đã biết ở 1 số version vLLM) -> KHÔNG bật cặp flag này (D3 dùng bản off)."
    )

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    out = results_dir / f"gate2_{args.label}.json"
    out.write_text(json.dumps({"label": args.label, **stats.as_dict()}, ensure_ascii=False, indent=2))
    print(f"Đã ghi {out}")


if __name__ == "__main__":
    main()
