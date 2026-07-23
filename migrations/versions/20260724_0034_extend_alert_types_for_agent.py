"""Extend alerts type constraints for agent investigation notifications.

Revision ID: 20260724_0034
Revises: 20260724_0033
Create Date: 2026-07-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260724_0034"
down_revision: str | Sequence[str] | None = "20260724_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ALERT_TYPES = "('INCIDENT_OPENED', 'INCIDENT_RECOVERED', 'DEPLOY_SUMMARY')"
NEW_ALERT_TYPES = (
    "('INCIDENT_OPENED', 'INCIDENT_RECOVERED', 'DEPLOY_SUMMARY', 'AGENT_INVESTIGATION')"
)
OLD_TRIGGER_TYPES = (
    "('SERVICE_CONNECTION_FAILURE', 'REPEATED_5XX_RESPONSE', "
    "'CRITICAL_SCENARIO_FAILURE', 'PERFORMANCE_SCORE_BELOW_THRESHOLD', "
    "'RESPONSE_TIME_ABOVE_THRESHOLD', 'DEPLOY_CHECK_COMPLETED')"
)
NEW_TRIGGER_TYPES = (
    "('SERVICE_CONNECTION_FAILURE', 'REPEATED_5XX_RESPONSE', "
    "'CRITICAL_SCENARIO_FAILURE', 'PERFORMANCE_SCORE_BELOW_THRESHOLD', "
    "'RESPONSE_TIME_ABOVE_THRESHOLD', 'DEPLOY_CHECK_COMPLETED', "
    "'AGENT_INVESTIGATION_COMPLETED')"
)


def upgrade() -> None:
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.create_check_constraint("ck_alerts_alert_type", "alerts", f"alert_type IN {NEW_ALERT_TYPES}")
    op.drop_constraint("ck_alerts_trigger_type", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_trigger_type", "alerts", f"trigger_type IN {NEW_TRIGGER_TYPES}"
    )


def downgrade() -> None:
    op.drop_constraint("ck_alerts_trigger_type", "alerts", type_="check")
    op.create_check_constraint(
        "ck_alerts_trigger_type", "alerts", f"trigger_type IN {OLD_TRIGGER_TYPES}"
    )
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.create_check_constraint("ck_alerts_alert_type", "alerts", f"alert_type IN {OLD_ALERT_TYPES}")
