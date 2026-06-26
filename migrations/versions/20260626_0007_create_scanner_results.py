"""Create scanner result tables.

Revision ID: 20260626_0007
Revises: 20260625_0006
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260626_0007"
down_revision: str | Sequence[str] | None = "20260625_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "availability_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("service_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("redirect_count", sa.Integer(), nullable=False),
        sa.Column("uses_https", sa.Boolean(), nullable=False),
        sa.Column("timed_out", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_availability_results_response_time_non_negative",
        ),
        sa.CheckConstraint(
            "redirect_count >= 0",
            name="ck_availability_results_redirect_count_non_negative",
        ),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_availability_results_check_run_id"),
        "availability_results",
        ["check_run_id"],
        unique=True,
    )

    op.create_table(
        "ssl_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("service_url", sa.String(length=2048), nullable=False),
        sa.Column("is_applicable", sa.Boolean(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("days_until_expiration", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ssl_results_check_run_id"),
        "ssl_results",
        ["check_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ssl_results_check_run_id"), table_name="ssl_results")
    op.drop_table("ssl_results")
    op.drop_index(
        op.f("ix_availability_results_check_run_id"),
        table_name="availability_results",
    )
    op.drop_table("availability_results")
