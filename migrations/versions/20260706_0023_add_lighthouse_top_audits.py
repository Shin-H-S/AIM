"""Add lighthouse top audits.

Revision ID: 20260706_0023
Revises: 20260705_0022
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_0023"
down_revision: str | Sequence[str] | None = "20260705_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lighthouse_results",
        sa.Column("top_audits", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lighthouse_results", "top_audits")
