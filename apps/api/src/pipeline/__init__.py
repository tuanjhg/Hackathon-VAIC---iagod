"""AI advisory pipeline package (stages S1–S8, per docs/architecture.md).

Provides the Need Profile conversation-state schema and its session store
(workflow doc §2, ADR C7), plus the S1 deterministic-preprocessing stage
(humanize + money/unit/category parsing, workflow doc §3). Later stages
(S2–S8) are added by separate work.
"""

from src.pipeline.humanize import NormalizeResult, normalize
from src.pipeline.need_profile import (
    DEFAULT_PRESERVED_SLOTS,
    MAX_CLARIFY_ROUNDS,
    NeedProfile,
)
from src.pipeline.preprocess import (
    CATEGORY_DICT,
    MoneyMatch,
    S1Result,
    UnitMatch,
    detect_category,
    parse_money,
    parse_units,
    run_s1,
)
from src.pipeline.session_store import (
    DEFAULT_TTL_SECONDS,
    InMemorySessionStore,
    SessionStore,
)
from src.pipeline.slots import SlotProfile, available_categories, load_slot_profile

__all__ = [
    "CATEGORY_DICT",
    "DEFAULT_PRESERVED_SLOTS",
    "DEFAULT_TTL_SECONDS",
    "MAX_CLARIFY_ROUNDS",
    "InMemorySessionStore",
    "MoneyMatch",
    "NeedProfile",
    "NormalizeResult",
    "S1Result",
    "SessionStore",
    "SlotProfile",
    "UnitMatch",
    "available_categories",
    "detect_category",
    "load_slot_profile",
    "normalize",
    "parse_money",
    "parse_units",
    "run_s1",
]
