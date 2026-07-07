"""Default project alert email to off.

Revision ID: 20260708_0025
Revises: 20260707_0024
Create Date: 2026-07-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260708_0025"
down_revision: str | Sequence[str] | None = "20260707_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "projects",
        "alert_email_enabled",
        server_default=sa.false(),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "projects",
        "alert_email_enabled",
        server_default=sa.true(),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
