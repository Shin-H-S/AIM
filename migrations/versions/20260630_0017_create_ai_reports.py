"""Create AI reports table.

Revision ID: 20260630_0017
Revises: 20260628_0016
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_0017"
down_revision: str | Sequence[str] | None = "20260628_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("input_schema_version", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=1), nullable=False),
        sa.Column("deployment_risk", sa.String(length=16), nullable=False),
        sa.Column("gate_reason", sa.Text(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_ai_reports_overall_score_range",
        ),
        sa.CheckConstraint(
            "grade IN ('A', 'B', 'C', 'D', 'F')",
            name="ck_ai_reports_grade",
        ),
        sa.CheckConstraint(
            "deployment_risk IN ('STABLE', 'WARNING', 'RISK')",
            name="ck_ai_reports_deployment_risk",
        ),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_reports_check_run_id"),
        "ai_reports",
        ["check_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_reports_check_run_id"), table_name="ai_reports")
    op.drop_table("ai_reports")
