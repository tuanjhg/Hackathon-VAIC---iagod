"""Record the catalog bridge application revision.

The real catalog uses independently managed source tables and therefore does
not require a structural change to the normalized API read model.

Revision ID: 20260718_0002
Revises: 20260717_0001
"""

from collections.abc import Sequence


revision: str = "20260718_0002"
down_revision: str | None = "20260717_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema change is required for the catalog synchronization layer."""


def downgrade() -> None:
    """No schema change was introduced by this revision."""
