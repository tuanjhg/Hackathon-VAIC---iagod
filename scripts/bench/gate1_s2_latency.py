#!/usr/bin/env python3
"""Benchmark Gate 1 — S2 (intent + slot extraction) p95 latency.

Quyết định treo (dmx-tech-decisions.md, bảng cuối #1):
    32B FP8 đạt p95 S2 <700ms? -> quyết định A3 (tách model nhỏ hay không).

Requires a running vLLM OpenAI-compatible endpoint (VLLM_BASE_URL). This
cannot be executed in the dev/build sandbox -- run it during the Phase 0
GPU window (master plan Sec 5b, W1). See scripts/bench/README.md.

Usage:
    python3 scripts/bench/gate1_s2_latency.py [--n 20]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import chat_completion, gate_verdict, summarize  # noqa: E402

THRESHOLD_P95_MS = 700

SYSTEM_PROMPT = (
    "Bạn trích xuất intent và slot từ tin nhắn khách mua sắm điện máy. "
    "Trả JSON đúng schema: "
    '{"intent": "tư_vấn|so_sánh_trực_tiếp|policy_faq|hỏi_chi_tiết_SP|ngoài_phạm_vi", '
    '"category": string|null, "slots_mới": object, "ngôn_ngữ_khách": "vi|en"}'
)

# Sample dirty-Vietnamese utterances, representative of S2's real input distribution
# (see dmx-ai-workflow-v1.md Sec 3 S1/S2 + Sec 4 edge cases).
SAMPLE_UTTERANCES = [
    "may lanh duoi 20tr phong 18m2 tiet kiem dien it on",
    "tủ lạnh cho gia đình 4 người, ngân sách 15 củ",
    "so sánh Daikin FTKY35 với Panasonic XU12 con nào hơn",
    "trả góp 0% cần gì không shop",
    "con thứ 2 có khuyến mãi gì không",
    "phòng ngủ nhỏ 12m2 không nắng, cần máy êm",
    "máy giặt inverter 9kg giá bao nhiêu",
    "thời tiết hôm nay thế nào",
    "muốn mua laptop gaming card rời",
    "20 củ có mua được máy lạnh inverter không",
]

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "intent_slot_extraction",
        "schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "category": {"type": ["string", "null"]},
                "slots_moi": {"type": "object"},
                "ngon_ngu_khach": {"type": "string"},
            },
            "required": ["intent", "slots_moi"],
        },
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20, help="số request mẫu (mặc định 20)")
    args = parser.parse_args()

    latencies: list[float] = []
    errors: list[str] = []
    for i in range(args.n):
        utterance = SAMPLE_UTTERANCES[i % len(SAMPLE_UTTERANCES)]
        result = chat_completion(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": utterance},
                ],
                "temperature": 0,
                "response_format": RESPONSE_FORMAT,
                # OpenRouter's own reasoning switch -- NOT vLLM's chat_template_kwargs
                # (confirmed 18/07: OpenRouter silently ignores chat_template_kwargs,
                # model reasons at length regardless, blowing latency/schema conformance).
                "reasoning": {"enabled": False},
            }
        )
        if result.ok:
            latencies.append(result.latency_s)
        else:
            errors.append(result.error or "unknown error")

    stats = summarize(latencies, errors)
    passed = stats.n_ok == args.n and stats.p95_ms < THRESHOLD_P95_MS

    print(f"Gate 1 -- S2 intent+slot p95 latency (target <{THRESHOLD_P95_MS}ms, n={args.n})")
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    print(gate_verdict(passed))
    if not passed and stats.n_ok < args.n:
        print(f"({args.n - stats.n_ok} request lỗi -- xem 'errors' ở trên)")

    Path(__file__).resolve().parent.joinpath("results").mkdir(exist_ok=True)
    out = Path(__file__).resolve().parent / "results" / "gate1_s2_latency.json"
    out.write_text(json.dumps({"passed": passed, **stats.as_dict()}, ensure_ascii=False, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
