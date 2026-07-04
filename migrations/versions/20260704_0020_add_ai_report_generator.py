"""Add AI report generator column.

Revision ID: 20260704_0020
Revises: 20260703_0019
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260704_0020"
down_revision: str | Sequence[str] | None = "20260703_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_reports",
        sa.Column(
            "generator",
            sa.String(length=80),
            server_default="deterministic",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_reports", "generator")
