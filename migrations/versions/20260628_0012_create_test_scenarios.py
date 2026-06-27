"""Create test scenarios tables.

Revision ID: 20260628_0012
Revises: 20260627_0011
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0012"
down_revision: str | Sequence[str] | None = "20260627_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_test_scenarios_project_id"),
        "test_scenarios",
        ["project_id"],
    )
    op.create_table(
        "test_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=2048), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("timeout_ms", sa.Integer(), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            (
                "action IN ('navigate', 'click', 'fill', 'wait', "
                "'assert_element_exists', 'assert_text_exists', 'assert_url', "
                "'take_screenshot')"
            ),
            name="ck_test_steps_action",
        ),
        sa.CheckConstraint("step_order > 0", name="ck_test_steps_step_order_positive"),
        sa.CheckConstraint(
            "timeout_ms IS NULL OR timeout_ms > 0",
            name="ck_test_steps_timeout_positive",
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["test_scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_test_steps_scenario_id"), "test_steps", ["scenario_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_test_steps_scenario_id"), table_name="test_steps")
    op.drop_table("test_steps")
    op.drop_index(op.f("ix_test_scenarios_project_id"), table_name="test_scenarios")
    op.drop_table("test_scenarios")
