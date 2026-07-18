"""OpenAI-compatible LLM router package (ADR A6).

Public interface for every LLM call in the pipeline: primary vLLM with a single
retry and an optional cloud fallback.
"""

from src.router.client import LLMRouter, LLMRouterError

__all__ = ["LLMRouter", "LLMRouterError"]
