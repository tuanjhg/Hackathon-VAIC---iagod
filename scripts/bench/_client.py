"""Shared HTTP + stats helpers for the 4 Phase 0 benchmark gates.

Stdlib-only (urllib) so gate1/gate2/gate4 need zero extra pip installs.
Talks to an OpenAI-compatible /chat/completions endpoint (vLLM serves this
natively). Point it at your running vLLM instance via env vars:

    VLLM_BASE_URL   default: http://localhost:8001/v1
    VLLM_MODEL      default: qwen3-32b-fp8
    VLLM_API_KEY    default: "" (vLLM ignores auth unless you configured one)
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8001/v1").rstrip("/")
MODEL = os.environ.get("VLLM_MODEL", "qwen3-32b-fp8")
API_KEY = os.environ.get("VLLM_API_KEY", "")
DEFAULT_TIMEOUT_S = float(os.environ.get("VLLM_TIMEOUT_S", "10"))


@dataclass
class CallResult:
    ok: bool
    latency_s: float
    ttft_s: float | None = None
    body: dict[str, Any] | None = None
    error: str | None = None


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def chat_completion(payload: dict[str, Any], timeout: float = DEFAULT_TIMEOUT_S) -> CallResult:
    """Non-streaming call. Returns whole-request latency."""
    body = {"model": MODEL, **payload}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=data, headers=_headers(), method="POST"
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            parsed = json.loads(resp.read())
        return CallResult(ok=True, latency_s=time.perf_counter() - start, body=parsed)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return CallResult(ok=False, latency_s=time.perf_counter() - start, error=str(exc))


def chat_completion_stream(
    payload: dict[str, Any], timeout: float = DEFAULT_TIMEOUT_S
) -> CallResult:
    """Streaming (SSE) call. Returns TTFT (time to first token) + total latency."""
    body = {"model": MODEL, "stream": True, **payload}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=data, headers=_headers(), method="POST"
    )
    start = time.perf_counter()
    ttft: float | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[len("data:") :].strip()
                if chunk == "[DONE]":
                    break
                if ttft is None:
                    ttft = time.perf_counter() - start
        return CallResult(ok=True, latency_s=time.perf_counter() - start, ttft_s=ttft)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return CallResult(ok=False, latency_s=time.perf_counter() - start, ttft_s=ttft, error=str(exc))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


@dataclass
class Stats:
    n: int
    n_ok: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "n_ok": self.n_ok,
            "p50_ms": round(self.p50_ms, 1),
            "p95_ms": round(self.p95_ms, 1),
            "p99_ms": round(self.p99_ms, 1),
            "max_ms": round(self.max_ms, 1),
            "mean_ms": round(self.mean_ms, 1),
            "errors": self.errors[:5],
        }


def summarize(latencies_s: list[float], errors: list[str] | None = None) -> Stats:
    ms = [x * 1000 for x in latencies_s]
    return Stats(
        n=len(ms) + len(errors or []),
        n_ok=len(ms),
        p50_ms=percentile(ms, 50),
        p95_ms=percentile(ms, 95),
        p99_ms=percentile(ms, 99),
        max_ms=max(ms) if ms else float("nan"),
        mean_ms=(sum(ms) / len(ms)) if ms else float("nan"),
        errors=errors or [],
    )


def gate_verdict(passed: bool) -> str:
    return "✅ PASS" if passed else "❌ FAIL"
