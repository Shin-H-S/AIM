"""Link scenario runs to check runs.

Revision ID: 20260628_0016
Revises: 20260628_0015
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0016"
down_revision: str | Sequence[str] | None = "20260628_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scenario_runs", sa.Column("check_run_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_scenario_runs_check_run_id"), "scenario_runs", ["check_run_id"])
    op.create_foreign_key(
        "fk_scenario_runs_check_run_id_check_runs",
        "scenario_runs",
        "check_runs",
        ["check_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_scenario_runs_check_run_id_check_runs",
        "scenario_runs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_scenario_runs_check_run_id"), table_name="scenario_runs")
    op.drop_column("scenario_runs", "check_run_id")
