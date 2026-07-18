from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base

# Cross-dialect JSON: JSONB on PostgreSQL (runtime), JSON on SQLite (tests) —
# same pattern as Product.specs_json.
_json = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base):
    """One advisory turn's audit record (guardrail Tầng 5, docs/pipelines.md §6.8).

    One table, three consumers: dev debugging, the eval harness, and the
    demand dashboard (ADR D4). ``user_message_masked`` is PII-masked *before*
    insert (H3) — raw customer text never reaches this table. The
    ``need_profile`` snapshot doubles as the per-turn ``need_profile_log`` the
    workflow doc §6.2 asks for.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    intent: Mapped[str] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    response_kind: Mapped[str] = mapped_column(String(30))
    user_message_masked: Mapped[str] = mapped_column(Text)

    need_profile: Mapped[dict[str, Any] | None] = mapped_column(_json, nullable=True)
    total_candidates: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict_counts: Mapped[dict[str, Any] | None] = mapped_column(_json, nullable=True)
    verifier_flags: Mapped[list[Any] | None] = mapped_column(_json, nullable=True)
    source_panel: Mapped[list[Any] | None] = mapped_column(_json, nullable=True)
    regenerated: Mapped[bool] = mapped_column(Boolean, default=False)
    used_fallback_table: Mapped[bool] = mapped_column(Boolean, default=False)
    timings_ms: Mapped[dict[str, Any] | None] = mapped_column(_json, nullable=True)
