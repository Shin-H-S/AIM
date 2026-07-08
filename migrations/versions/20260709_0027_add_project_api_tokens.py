"""Add project API tokens and check run deploy refs.

Revision ID: 20260709_0027
Revises: 20260708_0026
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260709_0027"
down_revision: str | Sequence[str] | None = "20260708_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_api_tokens_project_id"),
        "project_api_tokens",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_project_api_tokens_token_hash"),
        "project_api_tokens",
        ["token_hash"],
        unique=True,
    )
    op.add_column(
        "check_runs",
        sa.Column("deploy_ref", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("check_runs", "deploy_ref")
    op.drop_index(op.f("ix_project_api_tokens_token_hash"), table_name="project_api_tokens")
    op.drop_index(op.f("ix_project_api_tokens_project_id"), table_name="project_api_tokens")
    op.drop_table("project_api_tokens")
