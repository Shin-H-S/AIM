"""Add the webhook alert channel.

Revision ID: 20260708_0026
Revises: 20260708_0025
Create Date: 2026-07-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260708_0026"
down_revision: str | Sequence[str] | None = "20260708_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("alert_webhook_url", sa.String(length=1024), nullable=True),
    )
    op.drop_constraint("ck_alerts_channel", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_channel",
        "alerts",
        "channel IN ('EMAIL', 'WEBHOOK')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_alerts_channel", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_channel",
        "alerts",
        "channel IN ('EMAIL')",
    )
    op.drop_column("projects", "alert_webhook_url")
