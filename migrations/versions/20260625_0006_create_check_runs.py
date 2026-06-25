"""Create check runs table.

Revision ID: 20260625_0006
Revises: 20260625_0005
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260625_0006"
down_revision: str | Sequence[str] | None = "20260625_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "check_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'ANALYZING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_check_runs_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_check_runs_project_id"), "check_runs", ["project_id"], unique=False)
    op.create_index(
        op.f("ix_check_runs_requested_by_id"),
        "check_runs",
        ["requested_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_check_runs_requested_by_id"), table_name="check_runs")
    op.drop_index(op.f("ix_check_runs_project_id"), table_name="check_runs")
    op.drop_table("check_runs")
