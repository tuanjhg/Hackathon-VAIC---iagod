"""Lightweight OpenAI-compatible LLM router (ADR A6).

Every LLM call goes through one interface pointing at the local vLLM
(OpenAI-compatible ``/chat/completions``). On a timeout or an HTTP 5xx the
primary is retried exactly once; if it still fails the router either calls the
cloud fallback (when ``llm_fallback_enabled``) or raises :class:`LLMRouterError`.

This is the deliberately small, self-written client the ADR chose over a
LiteLLM proxy — it uses ``httpx`` directly, not the ``openai`` SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.core.config import Settings, get_settings


class LLMRouterError(RuntimeError):
    """Raised when the primary (plus its one retry) and any fallback all fail."""


@dataclass(frozen=True)
class _Endpoint:
    base_url: str
    api_key: str
    model: str


def _is_retryable(exc: Exception) -> bool:
    """Timeouts and HTTP 5xx are retryable/fallback-worthy; 4xx are not."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


class LLMRouter:
    """Route chat completions to a primary vLLM endpoint with cloud fallback."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # transport is injected only in tests (httpx.MockTransport); None in prod.
        self._transport = transport

    @property
    def _primary(self) -> _Endpoint:
        s = self._settings
        return _Endpoint(s.llm_base_url, s.llm_api_key, s.llm_model)

    @property
    def _fallback(self) -> _Endpoint:
        s = self._settings
        return _Endpoint(s.llm_fallback_base_url, s.llm_fallback_api_key, s.llm_fallback_model)

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Return the parsed OpenAI-compatible chat-completion response body.

        ``kwargs`` (e.g. ``temperature``, ``max_tokens``) are passed through into
        the request payload. Raises :class:`LLMRouterError` if every attempt fails.
        """
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._settings.llm_timeout_seconds,
        ) as client:
            last_exc: Exception | None = None

            # Primary vLLM: initial attempt + exactly one retry on timeout/5xx.
            for _ in range(2):
                try:
                    return await self._post(client, self._primary, messages, kwargs)
                except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                    if not _is_retryable(exc):
                        raise LLMRouterError(
                            f"LLM primary call failed (non-retryable): {exc}"
                        ) from exc
                    last_exc = exc

            # Primary exhausted. Fall back to cloud only if explicitly enabled.
            if self._settings.llm_fallback_enabled:
                try:
                    return await self._post(client, self._fallback, messages, kwargs)
                except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                    raise LLMRouterError(f"LLM fallback call also failed: {exc}") from exc

            raise LLMRouterError(
                "LLM primary call failed after retry and fallback is disabled: "
                f"{last_exc}"
            ) from last_exc

    async def _post(
        self,
        client: httpx.AsyncClient,
        endpoint: _Endpoint,
        messages: list[dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": endpoint.model, "messages": messages}
        payload.update(kwargs)
        headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}
        url = f"{endpoint.base_url.rstrip('/')}/chat/completions"

        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data
