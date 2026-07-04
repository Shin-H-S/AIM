"""Add project baseline check run.

Revision ID: 20260704_0021
Revises: 20260704_0020
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260704_0021"
down_revision: str | Sequence[str] | None = "20260704_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("baseline_check_run_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "baseline_check_run_id")
