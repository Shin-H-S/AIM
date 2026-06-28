"""Add scenario failure screenshot artifacts.

Revision ID: 20260628_0015
Revises: 20260628_0014
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0015"
down_revision: str | Sequence[str] | None = "20260628_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "artifacts",
        "check_run_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column("artifacts", sa.Column("scenario_run_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_artifacts_scenario_run_id"),
        "artifacts",
        ["scenario_run_id"],
    )
    op.create_foreign_key(
        "fk_artifacts_scenario_run_id_scenario_runs",
        "artifacts",
        "scenario_runs",
        ["scenario_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_artifacts_owner_present",
        "artifacts",
        "check_run_id IS NOT NULL OR scenario_run_id IS NOT NULL",
    )

    op.add_column(
        "step_results",
        sa.Column("failure_screenshot_artifact_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_step_results_failure_screenshot_artifact_id"),
        "step_results",
        ["failure_screenshot_artifact_id"],
    )
    op.create_foreign_key(
        "fk_step_results_failure_screenshot_artifact_id_artifacts",
        "step_results",
        "artifacts",
        ["failure_screenshot_artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_step_results_failure_screenshot_artifact_id_artifacts",
        "step_results",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_step_results_failure_screenshot_artifact_id"),
        table_name="step_results",
    )
    op.drop_column("step_results", "failure_screenshot_artifact_id")

    op.drop_constraint("ck_artifacts_owner_present", "artifacts", type_="check")
    op.drop_constraint(
        "fk_artifacts_scenario_run_id_scenario_runs",
        "artifacts",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_artifacts_scenario_run_id"), table_name="artifacts")
    op.drop_column("artifacts", "scenario_run_id")
    op.alter_column(
        "artifacts",
        "check_run_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
