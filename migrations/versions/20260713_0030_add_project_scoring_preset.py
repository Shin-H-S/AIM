"""Add per-project scoring preset.

Revision ID: 20260713_0030
Revises: 20260712_0029
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_0030"
down_revision: str | Sequence[str] | None = "20260712_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "scoring_preset",
            sa.String(length=32),
            nullable=False,
            server_default="service",
        ),
    )
    op.create_check_constraint(
        "ck_projects_scoring_preset",
        "projects",
        "scoring_preset IN ('service', 'content', 'internal')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_scoring_preset", "projects", type_="check")
    op.drop_column("projects", "scoring_preset")
