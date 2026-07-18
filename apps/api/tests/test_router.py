"""Tests for the OpenAI-compatible LLM router (ADR A6).

All HTTP is mocked with ``httpx.MockTransport`` — no real network calls.
The async ``LLMRouter.complete`` is driven via ``asyncio.run`` so we do not
depend on an async pytest plugin (none is installed).
"""

import asyncio

import httpx
import pytest

from src.core.config import Settings
from src.router import LLMRouter, LLMRouterError

PRIMARY_BASE_URL = "http://primary.test/v1"
FALLBACK_BASE_URL = "http://fallback.test/v1"


def make_settings(*, fallback_enabled: bool) -> Settings:
    return Settings(
        llm_base_url=PRIMARY_BASE_URL,
        llm_api_key="primary-key",
        llm_model="primary-model",
        llm_fallback_base_url=FALLBACK_BASE_URL,
        llm_fallback_api_key="fallback-key",
        llm_fallback_model="fallback-model",
        llm_fallback_enabled=fallback_enabled,
        llm_timeout_seconds=5.0,
    )


def ok_response(model: str = "primary-model", content: str = "hi") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        },
    )


def run_complete(router: LLMRouter) -> dict:
    return asyncio.run(router.complete([{"role": "user", "content": "hello"}]))


def test_success_on_first_try() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return ok_response()

    router = LLMRouter(
        settings=make_settings(fallback_enabled=False),
        transport=httpx.MockTransport(handler),
    )
    result = run_complete(router)

    assert result["choices"][0]["message"]["content"] == "hi"
    assert len(calls) == 1
    assert calls[0] == f"{PRIMARY_BASE_URL}/chat/completions"


def test_normal_200_does_not_trigger_retry_or_fallback() -> None:
    """A clean 200 on the very first call must hit the primary exactly once."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return ok_response()

    router = LLMRouter(
        settings=make_settings(fallback_enabled=True),  # enabled, but must not be used
        transport=httpx.MockTransport(handler),
    )
    run_complete(router)

    assert len(calls) == 1
    assert all(url.startswith(PRIMARY_BASE_URL) for url in calls)
    assert not any(url.startswith(FALLBACK_BASE_URL) for url in calls)


def test_retry_then_success_after_timeout() -> None:
    """First primary call times out, the single retry succeeds."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            raise httpx.ReadTimeout("primary timed out", request=request)
        return ok_response()

    router = LLMRouter(
        settings=make_settings(fallback_enabled=False),
        transport=httpx.MockTransport(handler),
    )
    result = run_complete(router)

    assert result["choices"][0]["message"]["content"] == "hi"
    assert len(calls) == 2
    assert all(url.startswith(PRIMARY_BASE_URL) for url in calls)


def test_retry_then_fallback_success_when_enabled() -> None:
    """Primary fails twice (5xx), fallback is enabled and succeeds."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url.startswith(PRIMARY_BASE_URL):
            return httpx.Response(503, json={"error": "vllm down"})
        return ok_response(model="fallback-model", content="from-fallback")

    router = LLMRouter(
        settings=make_settings(fallback_enabled=True),
        transport=httpx.MockTransport(handler),
    )
    result = run_complete(router)

    assert result["model"] == "fallback-model"
    assert result["choices"][0]["message"]["content"] == "from-fallback"
    primary_calls = [u for u in calls if u.startswith(PRIMARY_BASE_URL)]
    fallback_calls = [u for u in calls if u.startswith(FALLBACK_BASE_URL)]
    assert len(primary_calls) == 2  # original + one retry
    assert len(fallback_calls) == 1


def test_retry_then_raise_when_fallback_disabled() -> None:
    """Primary fails twice and fallback is off -> clear LLMRouterError, no fallback call."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url.startswith(PRIMARY_BASE_URL):
            raise httpx.ReadTimeout("primary timed out", request=request)
        return ok_response(model="fallback-model")

    router = LLMRouter(
        settings=make_settings(fallback_enabled=False),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMRouterError):
        run_complete(router)

    assert len(calls) == 2  # original + one retry, nothing else
    assert all(url.startswith(PRIMARY_BASE_URL) for url in calls)
    assert not any(url.startswith(FALLBACK_BASE_URL) for url in calls)
