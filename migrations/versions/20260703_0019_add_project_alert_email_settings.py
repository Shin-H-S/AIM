"""Add project alert email settings.

Revision ID: 20260703_0019
Revises: 20260701_0018
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260703_0019"
down_revision: str | Sequence[str] | None = "20260701_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "alert_email_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column("alert_recipient_email", sa.String(length=320), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "alert_recipient_email")
    op.drop_column("projects", "alert_email_enabled")
