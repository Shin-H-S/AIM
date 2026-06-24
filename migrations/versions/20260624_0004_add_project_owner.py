"""Add project ownership.

Revision ID: 20260624_0004
Revises: 20260624_0003
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0004"
down_revision: str | Sequence[str] | None = "20260624_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_foreign_key(
        "fk_projects_owner_id_users",
        "projects",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_owner_id_users", "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_column("projects", "owner_id")
