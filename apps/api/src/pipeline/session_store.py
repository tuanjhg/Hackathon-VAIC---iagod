"""Session store for Need Profile conversation state (ADR C7).

``SessionStore`` is the interface; ``InMemorySessionStore`` is the single-server
demo implementation — an in-memory dict with per-entry TTL and lazy expiry (no
background thread). Because callers depend only on the interface, a Redis-backed
implementation can replace it at pilot time without touching them.
"""

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from src.pipeline.need_profile import NeedProfile

DEFAULT_TTL_SECONDS = 1800  # 30 minutes


@runtime_checkable
class SessionStore(Protocol):
    """Storage interface for per-session Need Profiles."""

    def get(self, session_id: str) -> NeedProfile | None:
        """Return the profile for ``session_id``, or ``None`` if absent/expired."""
        ...

    def set(self, session_id: str, profile: NeedProfile) -> None:
        """Store (or replace) the profile for ``session_id``."""
        ...

    def delete(self, session_id: str) -> None:
        """Remove the profile for ``session_id``; a no-op if absent."""
        ...


class InMemorySessionStore:
    """Dict-backed :class:`SessionStore` with per-entry TTL and lazy expiry.

    An entry expires once ``clock() - stored_at > ttl_seconds``; expiry is
    checked (and the stale entry evicted) on access. ``set`` refreshes the
    timestamp. The clock is injectable so TTL behaviour is testable without
    sleeping; it defaults to :func:`time.monotonic`, which is immune to wall-
    clock adjustments.
    """

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, tuple[NeedProfile, float]] = {}

    def get(self, session_id: str) -> NeedProfile | None:
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        profile, stored_at = entry
        if self._clock() - stored_at > self._ttl_seconds:
            del self._entries[session_id]
            return None
        return profile

    def set(self, session_id: str, profile: NeedProfile) -> None:
        self._entries[session_id] = (profile, self._clock())

    def delete(self, session_id: str) -> None:
        self._entries.pop(session_id, None)
