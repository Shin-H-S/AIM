"""Allow deploy summary alerts without an incident.

Revision ID: 20260710_0028
Revises: 20260709_0027
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0028"
down_revision: str | Sequence[str] | None = "20260709_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INCIDENT_TRIGGER_TYPES = (
    "'SERVICE_CONNECTION_FAILURE', "
    "'REPEATED_5XX_RESPONSE', "
    "'CRITICAL_SCENARIO_FAILURE', "
    "'PERFORMANCE_SCORE_BELOW_THRESHOLD', "
    "'RESPONSE_TIME_ABOVE_THRESHOLD'"
)


def upgrade() -> None:
    op.alter_column(
        "alerts",
        "incident_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_alert_type",
        "alerts",
        "alert_type IN ('INCIDENT_OPENED', 'INCIDENT_RECOVERED', 'DEPLOY_SUMMARY')",
    )
    op.drop_constraint("ck_alerts_trigger_type", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_trigger_type",
        "alerts",
        f"trigger_type IN ({INCIDENT_TRIGGER_TYPES}, 'DEPLOY_CHECK_COMPLETED')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM alerts WHERE alert_type = 'DEPLOY_SUMMARY'")
    op.drop_constraint("ck_alerts_trigger_type", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_trigger_type",
        "alerts",
        f"trigger_type IN ({INCIDENT_TRIGGER_TYPES})",
    )
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_alert_type",
        "alerts",
        "alert_type IN ('INCIDENT_OPENED', 'INCIDENT_RECOVERED')",
    )
    op.alter_column(
        "alerts",
        "incident_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
