"""Add user feedback columns to agent investigations.

Revision ID: 20260728_0038
Revises: 20260728_0037
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0038"
down_revision: str | Sequence[str] | None = "20260728_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FEEDBACK_ROOT_CAUSES = (
    "'service_down', 'ssl_invalid', 'server_slow', "
    "'frontend_regression', 'ui_regression', 'scenario_stale', "
    "'measurement_noise'"
)


def upgrade() -> None:
    # 조사가 맞았는지에 대한 실운영 라벨을 모은다.
    #
    # ADR 0002는 게이트를 통과시킨 test 83건이 전부 합성이고 그 100%가
    # "합성 분포 안에서의 상한"이라고 스스로 못 박았다. 그런데 사용자가
    # 맞았다/틀렸다를 남길 채널이 없어, 실운영 정확도는 앞으로도 알 수 없는
    # 상태였다. 여기 쌓이는 값이 다음 게이트를 실데이터로 치기 위한 원자료다.
    op.add_column(
        "agent_investigations",
        sa.Column("feedback_verdict", sa.String(length=16), nullable=True),
    )
    # 틀렸다고 할 때 지목한 진짜 원인 — 라벨로서 가장 값어치 있는 값이다.
    op.add_column(
        "agent_investigations",
        sa.Column("feedback_root_cause", sa.String(length=32), nullable=True),
    )
    op.add_column("agent_investigations", sa.Column("feedback_note", sa.Text(), nullable=True))
    op.add_column(
        "agent_investigations",
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_investigations",
        sa.Column("feedback_by_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_investigations_feedback_by_id_users",
        "agent_investigations",
        "users",
        ["feedback_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_agent_investigations_feedback_verdict"),
        "agent_investigations",
        ["feedback_verdict"],
    )
    op.create_check_constraint(
        "ck_agent_investigations_feedback_verdict",
        "agent_investigations",
        "feedback_verdict IS NULL OR feedback_verdict IN ('accurate', 'inaccurate')",
    )
    op.create_check_constraint(
        "ck_agent_investigations_feedback_root_cause",
        "agent_investigations",
        f"feedback_root_cause IS NULL OR feedback_root_cause IN ({FEEDBACK_ROOT_CAUSES})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_investigations_feedback_root_cause",
        "agent_investigations",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_investigations_feedback_verdict",
        "agent_investigations",
        type_="check",
    )
    op.drop_index(
        op.f("ix_agent_investigations_feedback_verdict"),
        table_name="agent_investigations",
    )
    op.drop_constraint(
        "fk_agent_investigations_feedback_by_id_users",
        "agent_investigations",
        type_="foreignkey",
    )
    for column_name in (
        "feedback_by_id",
        "feedback_at",
        "feedback_note",
        "feedback_root_cause",
        "feedback_verdict",
    ):
        op.drop_column("agent_investigations", column_name)
