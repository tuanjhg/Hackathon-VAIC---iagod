"""add audit_logs table (guardrail Tầng 5, docs/pipelines.md §6.8)

Revision ID: 20260718_0004
Revises: 20260718_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0004"
down_revision: str | None = "20260718_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cross-dialect JSON: JSONB on PostgreSQL (runtime), JSON on SQLite (tests).
_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("response_kind", sa.String(length=30), nullable=False),
        sa.Column("user_message_masked", sa.Text(), nullable=False),
        sa.Column("need_profile", _json, nullable=True),
        sa.Column("total_candidates", sa.Integer(), nullable=True),
        sa.Column("verdict_counts", _json, nullable=True),
        sa.Column("verifier_flags", _json, nullable=True),
        sa.Column("source_panel", _json, nullable=True),
        sa.Column("regenerated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("used_fallback_table", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timings_ms", _json, nullable=True),
    )
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_session_id", table_name="audit_logs")
    op.drop_table("audit_logs")
