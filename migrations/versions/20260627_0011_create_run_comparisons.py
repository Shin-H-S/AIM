"""Create run comparisons table.

Revision ID: 20260627_0011
Revises: 20260627_0010
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0011"
down_revision: str | Sequence[str] | None = "20260627_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_check_run_id", sa.Uuid(), nullable=False),
        sa.Column("comparison_type", sa.String(length=32), nullable=False),
        sa.Column("overall_score_delta", sa.Integer(), nullable=True),
        sa.Column("availability_score_delta", sa.Integer(), nullable=True),
        sa.Column("web_performance_score_delta", sa.Integer(), nullable=True),
        sa.Column("accessibility_score_delta", sa.Integer(), nullable=True),
        sa.Column("seo_basic_quality_score_delta", sa.Integer(), nullable=True),
        sa.Column("response_time_delta_ms", sa.Integer(), nullable=True),
        sa.Column("performance_score_delta", sa.Integer(), nullable=True),
        sa.Column("deployment_risk_changed", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["baseline_check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_comparisons_baseline_check_run_id"),
        "run_comparisons",
        ["baseline_check_run_id"],
    )
    op.create_index(
        op.f("ix_run_comparisons_check_run_id"),
        "run_comparisons",
        ["check_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_run_comparisons_check_run_id"), table_name="run_comparisons")
    op.drop_index(
        op.f("ix_run_comparisons_baseline_check_run_id"),
        table_name="run_comparisons",
    )
    op.drop_table("run_comparisons")
