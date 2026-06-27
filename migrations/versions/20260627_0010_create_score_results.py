"""Create score results table.

Revision ID: 20260627_0010
Revises: 20260627_0009
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0010"
down_revision: str | Sequence[str] | None = "20260627_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "score_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("availability_score", sa.Integer(), nullable=True),
        sa.Column("functional_stability_score", sa.Integer(), nullable=True),
        sa.Column("web_performance_score", sa.Integer(), nullable=True),
        sa.Column("accessibility_score", sa.Integer(), nullable=True),
        sa.Column("seo_basic_quality_score", sa.Integer(), nullable=True),
        sa.Column("regression_stability_score", sa.Integer(), nullable=True),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("evaluated_weight", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=1), nullable=False),
        sa.Column("deployment_risk", sa.String(length=16), nullable=False),
        sa.Column("gate_reason", sa.Text(), nullable=True),
        sa.Column("scoring_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "availability_score IS NULL OR (availability_score >= 0 AND availability_score <= 100)",
            name="ck_score_results_availability_score_range",
        ),
        sa.CheckConstraint(
            "functional_stability_score IS NULL OR "
            "(functional_stability_score >= 0 AND functional_stability_score <= 100)",
            name="ck_score_results_functional_stability_score_range",
        ),
        sa.CheckConstraint(
            "web_performance_score IS NULL OR "
            "(web_performance_score >= 0 AND web_performance_score <= 100)",
            name="ck_score_results_web_performance_score_range",
        ),
        sa.CheckConstraint(
            "accessibility_score IS NULL OR "
            "(accessibility_score >= 0 AND accessibility_score <= 100)",
            name="ck_score_results_accessibility_score_range",
        ),
        sa.CheckConstraint(
            "seo_basic_quality_score IS NULL OR "
            "(seo_basic_quality_score >= 0 AND seo_basic_quality_score <= 100)",
            name="ck_score_results_seo_basic_quality_score_range",
        ),
        sa.CheckConstraint(
            "regression_stability_score IS NULL OR "
            "(regression_stability_score >= 0 AND regression_stability_score <= 100)",
            name="ck_score_results_regression_stability_score_range",
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_score_results_overall_score_range",
        ),
        sa.CheckConstraint(
            "evaluated_weight >= 0 AND evaluated_weight <= 100",
            name="ck_score_results_evaluated_weight_range",
        ),
        sa.CheckConstraint(
            "grade IN ('A', 'B', 'C', 'D', 'F')",
            name="ck_score_results_grade",
        ),
        sa.CheckConstraint(
            "deployment_risk IN ('STABLE', 'WARNING', 'RISK')",
            name="ck_score_results_deployment_risk",
        ),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_score_results_check_run_id"),
        "score_results",
        ["check_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_score_results_check_run_id"), table_name="score_results")
    op.drop_table("score_results")
