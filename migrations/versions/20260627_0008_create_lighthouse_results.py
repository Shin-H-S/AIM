"""Create lighthouse results table.

Revision ID: 20260627_0008
Revises: 20260626_0007
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0008"
down_revision: str | Sequence[str] | None = "20260626_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lighthouse_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("service_url", sa.String(length=2048), nullable=False),
        sa.Column("is_successful", sa.Boolean(), nullable=False),
        sa.Column("performance_score", sa.Integer(), nullable=True),
        sa.Column("accessibility_score", sa.Integer(), nullable=True),
        sa.Column("seo_score", sa.Integer(), nullable=True),
        sa.Column("best_practices_score", sa.Integer(), nullable=True),
        sa.Column("largest_contentful_paint_ms", sa.Integer(), nullable=True),
        sa.Column("cumulative_layout_shift", sa.Float(), nullable=True),
        sa.Column("total_blocking_time_ms", sa.Integer(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "performance_score IS NULL OR (performance_score >= 0 AND performance_score <= 100)",
            name="ck_lighthouse_results_performance_score_range",
        ),
        sa.CheckConstraint(
            "accessibility_score IS NULL OR "
            "(accessibility_score >= 0 AND accessibility_score <= 100)",
            name="ck_lighthouse_results_accessibility_score_range",
        ),
        sa.CheckConstraint(
            "seo_score IS NULL OR (seo_score >= 0 AND seo_score <= 100)",
            name="ck_lighthouse_results_seo_score_range",
        ),
        sa.CheckConstraint(
            "best_practices_score IS NULL OR "
            "(best_practices_score >= 0 AND best_practices_score <= 100)",
            name="ck_lighthouse_results_best_practices_score_range",
        ),
        sa.CheckConstraint(
            "largest_contentful_paint_ms IS NULL OR largest_contentful_paint_ms >= 0",
            name="ck_lighthouse_results_lcp_non_negative",
        ),
        sa.CheckConstraint(
            "cumulative_layout_shift IS NULL OR cumulative_layout_shift >= 0",
            name="ck_lighthouse_results_cls_non_negative",
        ),
        sa.CheckConstraint(
            "total_blocking_time_ms IS NULL OR total_blocking_time_ms >= 0",
            name="ck_lighthouse_results_tbt_non_negative",
        ),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lighthouse_results_check_run_id"),
        "lighthouse_results",
        ["check_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lighthouse_results_check_run_id"), table_name="lighthouse_results")
    op.drop_table("lighthouse_results")
