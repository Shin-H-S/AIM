"""Create projects table.

Revision ID: 20260624_0002
Revises: 20260623_0001
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0002"
down_revision: str | Sequence[str] | None = "20260623_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("service_url", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("scan_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("response_time_threshold_ms", sa.Integer(), nullable=False),
        sa.Column("quality_score_threshold", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "environment IN ('development', 'staging', 'production')",
            name="ck_projects_environment",
        ),
        sa.CheckConstraint(
            "scan_interval_minutes > 0",
            name="ck_projects_scan_interval_positive",
        ),
        sa.CheckConstraint(
            "response_time_threshold_ms > 0",
            name="ck_projects_response_time_threshold_positive",
        ),
        sa.CheckConstraint(
            "quality_score_threshold >= 0 AND quality_score_threshold <= 100",
            name="ck_projects_quality_score_threshold_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("projects")
