"""Add project scheduled scans opt-in.

Revision ID: 20260705_0022
Revises: 20260704_0021
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260705_0022"
down_revision: str | Sequence[str] | None = "20260704_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "scheduled_scans_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "scheduled_scans_enabled")
