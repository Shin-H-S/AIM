"""Create artifacts table.

Revision ID: 20260627_0009
Revises: 20260627_0008
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0009"
down_revision: str | Sequence[str] | None = "20260627_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_run_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_path", sa.String(length=2048), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_artifacts_size_bytes_non_negative",
        ),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifacts_check_run_id"), "artifacts", ["check_run_id"])

    op.add_column("lighthouse_results", sa.Column("raw_json_artifact_id", sa.Uuid()))
    op.create_index(
        op.f("ix_lighthouse_results_raw_json_artifact_id"),
        "lighthouse_results",
        ["raw_json_artifact_id"],
    )
    op.create_foreign_key(
        "fk_lighthouse_results_raw_json_artifact_id_artifacts",
        "lighthouse_results",
        "artifacts",
        ["raw_json_artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("lighthouse_results", "raw_json")


def downgrade() -> None:
    op.add_column("lighthouse_results", sa.Column("raw_json", sa.JSON()))
    op.drop_constraint(
        "fk_lighthouse_results_raw_json_artifact_id_artifacts",
        "lighthouse_results",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_lighthouse_results_raw_json_artifact_id"),
        table_name="lighthouse_results",
    )
    op.drop_column("lighthouse_results", "raw_json_artifact_id")

    op.drop_index(op.f("ix_artifacts_check_run_id"), table_name="artifacts")
    op.drop_table("artifacts")
