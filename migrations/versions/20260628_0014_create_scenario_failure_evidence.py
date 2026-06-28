"""Create scenario failure evidence tables.

Revision ID: 20260628_0014
Revises: 20260628_0013
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0014"
down_revision: str | Sequence[str] | None = "20260628_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "console_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_run_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("column_number", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "line_number IS NULL OR line_number >= 0",
            name="ck_console_errors_line_number_non_negative",
        ),
        sa.CheckConstraint(
            "column_number IS NULL OR column_number >= 0",
            name="ck_console_errors_column_number_non_negative",
        ),
        sa.ForeignKeyConstraint(["scenario_run_id"], ["scenario_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_console_errors_scenario_run_id"),
        "console_errors",
        ["scenario_run_id"],
    )

    op.create_table(
        "network_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_run_id", sa.Uuid(), nullable=False),
        sa.Column("request_url", sa.String(length=2048), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("failure_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["scenario_run_id"], ["scenario_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_network_failures_scenario_run_id"),
        "network_failures",
        ["scenario_run_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_network_failures_scenario_run_id"), table_name="network_failures")
    op.drop_table("network_failures")
    op.drop_index(op.f("ix_console_errors_scenario_run_id"), table_name="console_errors")
    op.drop_table("console_errors")
