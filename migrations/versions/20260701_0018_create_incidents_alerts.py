"""Create incidents and alerts tables.

Revision ID: 20260701_0018
Revises: 20260630_0017
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260701_0018"
down_revision: str | Sequence[str] | None = "20260630_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INCIDENT_TRIGGER_CHECK = (
    "trigger_type IN ("
    "'SERVICE_CONNECTION_FAILURE', "
    "'REPEATED_5XX_RESPONSE', "
    "'CRITICAL_SCENARIO_FAILURE', "
    "'PERFORMANCE_SCORE_BELOW_THRESHOLD', "
    "'RESPONSE_TIME_ABOVE_THRESHOLD')"
)


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("opened_check_run_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_check_run_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(INCIDENT_TRIGGER_CHECK, name="ck_incidents_trigger_type"),
        sa.CheckConstraint("severity IN ('WARNING', 'RISK')", name="ck_incidents_severity"),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_incidents_status"),
        sa.CheckConstraint(
            "(status = 'OPEN' AND resolved_at IS NULL) OR "
            "(status = 'RESOLVED' AND resolved_at IS NOT NULL)",
            name="ck_incidents_resolved_at_matches_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opened_check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_check_run_id"],
            ["check_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incidents_project_id"), "incidents", ["project_id"], unique=False)
    op.create_index(
        op.f("ix_incidents_opened_check_run_id"),
        "incidents",
        ["opened_check_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incidents_resolved_check_run_id"),
        "incidents",
        ["resolved_check_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)
    op.create_index(
        op.f("ix_incidents_trigger_type"),
        "incidents",
        ["trigger_type"],
        unique=False,
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=True),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "alert_type IN ('INCIDENT_OPENED', 'INCIDENT_RECOVERED')",
            name="ck_alerts_alert_type",
        ),
        sa.CheckConstraint(INCIDENT_TRIGGER_CHECK, name="ck_alerts_trigger_type"),
        sa.CheckConstraint("channel IN ('EMAIL')", name="ck_alerts_channel"),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_alerts_status"),
        sa.CheckConstraint(
            "delivery_attempts >= 0",
            name="ck_alerts_delivery_attempts_non_negative",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alerts_project_id"), "alerts", ["project_id"], unique=False)
    op.create_index(op.f("ix_alerts_incident_id"), "alerts", ["incident_id"], unique=False)
    op.create_index(op.f("ix_alerts_check_run_id"), "alerts", ["check_run_id"], unique=False)
    op.create_index(op.f("ix_alerts_status"), "alerts", ["status"], unique=False)
    op.create_index(op.f("ix_alerts_trigger_type"), "alerts", ["trigger_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alerts_trigger_type"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_status"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_check_run_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_incident_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_project_id"), table_name="alerts")
    op.drop_table("alerts")

    op.drop_index(op.f("ix_incidents_trigger_type"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_resolved_check_run_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_opened_check_run_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_project_id"), table_name="incidents")
    op.drop_table("incidents")
