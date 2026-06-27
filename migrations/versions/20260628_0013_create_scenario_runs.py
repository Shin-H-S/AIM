"""Create scenario runs tables.

Revision ID: 20260628_0013
Revises: 20260628_0012
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0013"
down_revision: str | Sequence[str] | None = "20260628_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_scenario_runs_status",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_scenario_runs_duration_non_negative",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["test_scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scenario_runs_project_id"), "scenario_runs", ["project_id"])
    op.create_index(
        op.f("ix_scenario_runs_requested_by_id"),
        "scenario_runs",
        ["requested_by_id"],
    )
    op.create_index(op.f("ix_scenario_runs_scenario_id"), "scenario_runs", ["scenario_id"])

    op.create_table(
        "step_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_run_id", sa.Uuid(), nullable=False),
        sa.Column("test_step_id", sa.Uuid(), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('PASSED', 'FAILED', 'SKIPPED')",
            name="ck_step_results_status",
        ),
        sa.CheckConstraint("step_order > 0", name="ck_step_results_step_order_positive"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_step_results_duration_non_negative",
        ),
        sa.ForeignKeyConstraint(["scenario_run_id"], ["scenario_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_step_id"], ["test_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_step_results_scenario_run_id"), "step_results", ["scenario_run_id"])
    op.create_index(op.f("ix_step_results_test_step_id"), "step_results", ["test_step_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_step_results_test_step_id"), table_name="step_results")
    op.drop_index(op.f("ix_step_results_scenario_run_id"), table_name="step_results")
    op.drop_table("step_results")
    op.drop_index(op.f("ix_scenario_runs_scenario_id"), table_name="scenario_runs")
    op.drop_index(op.f("ix_scenario_runs_requested_by_id"), table_name="scenario_runs")
    op.drop_index(op.f("ix_scenario_runs_project_id"), table_name="scenario_runs")
    op.drop_table("scenario_runs")
