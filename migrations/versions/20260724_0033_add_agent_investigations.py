"""Add agent_investigations for the investigation agent.

Revision ID: 20260724_0033
Revises: 20260717_0032
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0033"
down_revision: str | Sequence[str] | None = "20260717_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_investigations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("root_cause", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("generator", sa.String(length=64), nullable=False),
        sa.Column("recheck_used", sa.Boolean(), nullable=False),
        sa.Column("recheck_check_run_id", sa.Uuid(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("violations", sa.JSON(), nullable=False),
        sa.Column("llm_calls", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            (
                "root_cause IN ("
                "'service_down', 'ssl_invalid', 'server_slow', "
                "'frontend_regression', 'ui_regression', 'scenario_stale', "
                "'measurement_noise')"
            ),
            name="ck_agent_investigations_root_cause",
        ),
        sa.CheckConstraint(
            "trigger IN ('incident', 'manual')",
            name="ck_agent_investigations_trigger",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name="ck_agent_investigations_duration_non_negative",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recheck_check_run_id"], ["check_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_investigations_project_id", "agent_investigations", ["project_id"])
    op.create_index(
        "ix_agent_investigations_check_run_id",
        "agent_investigations",
        ["check_run_id"],
        unique=True,
    )
    op.create_index("ix_agent_investigations_incident_id", "agent_investigations", ["incident_id"])
    op.create_index(
        "ix_agent_investigations_recheck_check_run_id",
        "agent_investigations",
        ["recheck_check_run_id"],
    )
    op.create_index("ix_agent_investigations_root_cause", "agent_investigations", ["root_cause"])


def downgrade() -> None:
    op.drop_index("ix_agent_investigations_root_cause", table_name="agent_investigations")
    op.drop_index("ix_agent_investigations_recheck_check_run_id", table_name="agent_investigations")
    op.drop_index("ix_agent_investigations_incident_id", table_name="agent_investigations")
    op.drop_index("ix_agent_investigations_check_run_id", table_name="agent_investigations")
    op.drop_index("ix_agent_investigations_project_id", table_name="agent_investigations")
    op.drop_table("agent_investigations")
