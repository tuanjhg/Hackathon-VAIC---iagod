"""add multi-category jsonb specs to products"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0002"
down_revision: str | None = "20260717_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cross-dialect JSON: JSONB on PostgreSQL (runtime), JSON on SQLite (tests).
_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("products", sa.Column("category_key", sa.String(), nullable=True))
    op.add_column("products", sa.Column("specs", _json, nullable=True))
    op.add_column("products", sa.Column("specs_raw", _json, nullable=True))


def downgrade() -> None:
    op.drop_column("products", "specs_raw")
    op.drop_column("products", "specs")
    op.drop_column("products", "category_key")
