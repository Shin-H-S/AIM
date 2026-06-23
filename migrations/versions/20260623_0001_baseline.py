"""Create the initial database baseline.

Revision ID: 20260623_0001
Revises:
Create Date: 2026-06-23
"""

from collections.abc import Sequence

revision: str = "20260623_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the migration history before domain tables are added."""


def downgrade() -> None:
    """Remove no schema objects because the baseline is intentionally empty."""
