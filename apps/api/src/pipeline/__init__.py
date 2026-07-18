"""AI advisory pipeline package (stages S1–S8, per docs/architecture.md).

Currently provides the Need Profile conversation-state schema and its session
store (workflow doc §2, ADR C7). The S1–S8 stage modules are added by separate
work; this package intentionally keeps the Need Profile self-contained.
"""

from src.pipeline.need_profile import (
    DEFAULT_PRESERVED_SLOTS,
    MAX_CLARIFY_ROUNDS,
    NeedProfile,
)
from src.pipeline.session_store import (
    DEFAULT_TTL_SECONDS,
    InMemorySessionStore,
    SessionStore,
)

__all__ = [
    "DEFAULT_PRESERVED_SLOTS",
    "DEFAULT_TTL_SECONDS",
    "MAX_CLARIFY_ROUNDS",
    "InMemorySessionStore",
    "NeedProfile",
    "SessionStore",
]
