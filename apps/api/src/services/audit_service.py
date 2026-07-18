"""Best-effort audit-log writer (guardrail Tầng 5, ADR D4).

Persists one :class:`~src.models.audit_log.AuditLog` row per advisory turn.
Writing is deliberately best-effort: an audit failure must never break the
customer-facing reply, so every exception is logged and swallowed here — the
one place in the codebase where swallowing is the contract, not a bug.
"""

from collections import Counter
from logging import getLogger

from sqlalchemy.orm import Session

from src.models import AuditLog
from src.pipeline.orchestrator import TurnResult
from src.pipeline.s8_respond import mask_pii

logger = getLogger(__name__)


def write_audit_log(
    db: Session, *, session_id: str, user_text: str, result: TurnResult
) -> AuditLog | None:
    """Insert the turn's audit row; returns it, or ``None`` on failure.

    ``user_text`` is PII-masked before it ever touches the ORM object (H3).
    """
    try:
        verdict_counts: dict[str, int] = {}
        if result.verification is not None:
            verdict_counts = dict(Counter(c.verdict for c in result.verification.claims))

        row = AuditLog(
            session_id=session_id,
            intent=result.intent,
            category=result.profile.category,
            response_kind=result.kind,
            user_message_masked=mask_pii(user_text),
            need_profile=result.profile.model_dump(),
            total_candidates=result.total_candidates,
            verdict_counts=verdict_counts,
            verifier_flags=[flag.model_dump() for flag in result.verifier_flags],
            source_panel=[entry.model_dump() for entry in result.source_panel],
            regenerated=result.regenerated,
            used_fallback_table=result.used_fallback_table,
            timings_ms=result.timings_ms,
        )
        db.add(row)
        db.commit()
        return row
    except Exception:
        logger.exception("audit_log write failed for session %s", session_id)
        db.rollback()
        return None
