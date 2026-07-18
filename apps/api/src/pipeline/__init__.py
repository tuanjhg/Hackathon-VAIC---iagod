"""AI advisory pipeline package (stages S1–S8, per docs/architecture.md).

Provides the Need Profile conversation-state schema and its session store
(workflow doc §2, ADR C7), the S1 deterministic-preprocessing stage (humanize
+ money/unit/category parsing, workflow doc §3), S2 intent+slot extraction
(ADR C2), S3 dialogue policy (ADR C3), S5 fit-score ranking (ADR C4/C5),
S6 statement-template generation (ADR A8/C5) and the turn orchestrator that
wires them for the ``tu_van`` branch. S4 lives in `src.tools.catalog_search`
(it's a tool, not a pipeline module); S7 is `src.verifier`; S8 (respond +
source panel + audit log) is separate, later work.
"""

from src.pipeline.humanize import NormalizeResult, normalize
from src.pipeline.need_profile import (
    DEFAULT_PRESERVED_SLOTS,
    MAX_CLARIFY_ROUNDS,
    NeedProfile,
)
from src.pipeline.orchestrator import (
    DEFAULT_RETRIEVE_LIMIT,
    CandidateRetriever,
    FactsToolLike,
    RetrievalResult,
    TurnResult,
    run_turn,
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
from src.pipeline.s2_extract import (
    INTENTS,
    LLMRouterLike,
    S2ExtractionError,
    S2Result,
    build_response_format,
    extract,
)
from src.pipeline.s3_policy import (
    HIGH_CANDIDATE_THRESHOLD,
    LOW_CANDIDATE_THRESHOLD,
    MAX_ASK_BATCH,
    PolicyDecision,
    decide_policy,
)
from src.pipeline.s5_ranking import (
    BUDGET_SLOT_NAME,
    PRIORITY_SLOT_NAME,
    RankingResult,
    ScoreBreakdown,
    TradeOff,
    rank_candidates,
)
from src.pipeline.s8_respond import (
    MAX_INCIDENTS,
    EnforcementResult,
    SourceEntry,
    VerifierFlag,
    build_source_panel,
    enforce,
    mask_pii,
    render_fallback_table,
)
from src.pipeline.session_store import (
    DEFAULT_TTL_SECONDS,
    InMemorySessionStore,
    SessionStore,
)
from src.pipeline.slots import SlotProfile, available_categories, load_slot_profile

__all__ = [
    "BUDGET_SLOT_NAME",
    "CATEGORY_DICT",
    "DEFAULT_PRESERVED_SLOTS",
    "DEFAULT_RETRIEVE_LIMIT",
    "DEFAULT_TTL_SECONDS",
    "HIGH_CANDIDATE_THRESHOLD",
    "INTENTS",
    "LOW_CANDIDATE_THRESHOLD",
    "MAX_ASK_BATCH",
    "MAX_CLARIFY_ROUNDS",
    "MAX_INCIDENTS",
    "PRIORITY_SLOT_NAME",
    "CandidateRetriever",
    "EnforcementResult",
    "FactsToolLike",
    "InMemorySessionStore",
    "LLMRouterLike",
    "RetrievalResult",
    "SourceEntry",
    "TurnResult",
    "VerifierFlag",
    "MoneyMatch",
    "NeedProfile",
    "NormalizeResult",
    "PolicyDecision",
    "RankingResult",
    "S1Result",
    "S2ExtractionError",
    "S2Result",
    "ScoreBreakdown",
    "SessionStore",
    "SlotProfile",
    "TradeOff",
    "UnitMatch",
    "available_categories",
    "build_response_format",
    "build_source_panel",
    "decide_policy",
    "detect_category",
    "enforce",
    "extract",
    "load_slot_profile",
    "mask_pii",
    "normalize",
    "parse_money",
    "parse_units",
    "rank_candidates",
    "render_fallback_table",
    "run_s1",
    "run_turn",
]
