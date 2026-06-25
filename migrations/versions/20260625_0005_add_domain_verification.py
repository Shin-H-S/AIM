"""Add domain verification fields.

Revision ID: 20260625_0005
Revises: 20260624_0004
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260625_0005"
down_revision: str | Sequence[str] | None = "20260624_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("verification_token", sa.String(length=128), nullable=True))
    op.add_column("projects", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_projects_verification_token"),
        "projects",
        ["verification_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_verification_token"), table_name="projects")
    op.drop_column("projects", "verified_at")
    op.drop_column("projects", "verification_token")
