#!/usr/bin/env python3
"""Benchmark Gate 4 -- Qwen3 (thinking off) + guided_json + hermes tool-call, clean run.

Quyết định treo (dmx-tech-decisions.md, bảng cuối #4):
    Qwen3-32B tắt thinking hoạt động sạch với guided_json + hermes tools?
    -> quyết định A2 (giữ Qwen3 hay lùi Qwen2.5-32B-Instruct).

10 lần gọi: 5 guided_json thuần (mô phỏng S2), 5 có tool definition + kỳ
vọng model tự chọn gọi tool (mô phỏng nhánh hỏi_chi_tiết_SP, ADR A5).
Pass = cả 10 đều parse sạch, không lỗi JSON / tool-call malformed.

Requires a running vLLM OpenAI-compatible endpoint serving Qwen3-32B with
`--enable-auto-tool-choice --tool-call-parser hermes` (or equivalent for
your vLLM version). Cannot be executed in this sandbox -- run it during
the Phase 0 GPU window (master plan Sec 5b, W1). See scripts/bench/README.md.

Usage:
    python3 scripts/bench/gate4_qwen3_clean_run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import chat_completion  # noqa: E402

JSON_ONLY_CASES = [
    "may lanh duoi 20tr phong 18m2",
    "tủ lạnh 4 người ngân sách 15tr",
    "so sánh Daikin FTKY35 với Panasonic XU12",
    "trả góp 0% cần gì",
    "thời tiết hôm nay sao rồi",
]

TOOL_CASES = [
    "con Daikin FTKY35 kia có khuyến mãi gì không",
    "check giúp em con Panasonic XU12 còn hàng không",
    "giá con thứ 2 hiện tại bao nhiêu",
    "con máy lạnh mã 180706 công suất bao nhiêu BTU",
    "cho em xem đánh giá của con tủ lạnh Samsung 313 lít",
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
            },
            "required": ["intent", "slots_moi"],
        },
    },
}

CATALOG_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "catalog_search",
        "description": "Tìm sản phẩm trong catalog theo điều kiện lọc cứng",
        "parameters": {
            "type": "object",
            "properties": {
                "model_code_or_name": {"type": "string"},
                "category": {"type": "string"},
            },
            "required": [],
        },
    },
}

# OpenRouter's own reasoning switch -- NOT vLLM's chat_template_kwargs (confirmed
# 18/07: OpenRouter silently ignores chat_template_kwargs, model reasons at length
# regardless, blowing latency/schema conformance).
REASONING_OFF = {"enabled": False}


def run_json_case(utterance: str) -> tuple[bool, str]:
    result = chat_completion(
        {
            "messages": [
                {"role": "system", "content": "Trích intent+slot, trả đúng JSON schema."},
                {"role": "user", "content": utterance},
            ],
            "temperature": 0,
            "response_format": RESPONSE_FORMAT,
            "reasoning": REASONING_OFF,
        }
    )
    if not result.ok or result.body is None:
        return False, result.error or "no response"
    try:
        content = result.body["choices"][0]["message"]["content"]
        json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return False, f"parse error: {exc}"
    return True, "ok"


def run_tool_case(utterance: str) -> tuple[bool, str]:
    result = chat_completion(
        {
            "messages": [
                {
                    "role": "system",
                    "content": "Trả lời câu hỏi chi tiết sản phẩm bằng cách gọi tool catalog_search.",
                },
                {"role": "user", "content": utterance},
            ],
            "temperature": 0,
            "tools": [CATALOG_SEARCH_TOOL],
            "tool_choice": "auto",
            "reasoning": REASONING_OFF,
        }
    )
    if not result.ok or result.body is None:
        return False, result.error or "no response"
    try:
        message = result.body["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return False, "model không gọi tool (có thể chấp nhận được tùy prompt -- xem log)"
        for call in tool_calls:
            json.loads(call["function"]["arguments"])  # must be valid JSON
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        return False, f"tool-call malformed: {exc}"
    return True, "ok"


def main() -> None:
    results = []
    for utterance in JSON_ONLY_CASES:
        ok, detail = run_json_case(utterance)
        results.append({"case": "json_only", "input": utterance, "ok": ok, "detail": detail})
    for utterance in TOOL_CASES:
        ok, detail = run_tool_case(utterance)
        results.append({"case": "tool_call", "input": utterance, "ok": ok, "detail": detail})

    n_ok = sum(1 for r in results if r["ok"])
    passed = n_ok == len(results)

    print(f"Gate 4 -- Qwen3 tắt thinking, guided_json + hermes tool-call, clean run (10 call)")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"{n_ok}/{len(results)} clean -- {'✅ PASS' if passed else '❌ FAIL (lùi Qwen2.5-32B-Instruct)'}")

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    out = results_dir / "gate4_qwen3_clean_run.json"
    out.write_text(json.dumps({"passed": passed, "n_ok": n_ok, "results": results}, ensure_ascii=False, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
