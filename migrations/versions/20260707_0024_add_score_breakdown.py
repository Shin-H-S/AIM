"""Add score breakdown.

Revision ID: 20260707_0024
Revises: 20260706_0023
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0024"
down_revision: str | Sequence[str] | None = "20260706_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "score_results",
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("score_results", "score_breakdown")
