"""Add composite indexes for the paginated list queries.

Revision ID: 20260728_0037
Revises: 20260728_0036
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0037"
down_revision: str | Sequence[str] | None = "20260728_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모든 목록 화면이 "소유 컬럼으로 좁히고 최신순으로 정렬해 한 페이지"를 읽는다.
# 지금까지 인덱스는 전부 단일 컬럼이라, PostgreSQL은 소유 컬럼으로 좁힌 뒤
# 정렬을 따로 해야 했다. 행이 쌓일수록 대시보드가 느려지는 구조다 —
# 성능 회귀를 감지하는 제품의 대시보드가 느려지는 것은 특히 나쁘다.
#
# 정렬 방향까지 인덱스에 넣어야 역방향 스캔 없이 그대로 읽는다.
LIST_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_check_runs_project_id_created_at", "check_runs", "project_id, created_at DESC"),
    ("ix_projects_owner_id_created_at", "projects", "owner_id, created_at DESC"),
    ("ix_test_scenarios_project_id_created_at", "test_scenarios", "project_id, created_at DESC"),
    (
        "ix_scenario_runs_scenario_id_created_at",
        "scenario_runs",
        "scenario_id, created_at DESC",
    ),
    ("ix_incidents_project_id_started_at", "incidents", "project_id, started_at DESC, id DESC"),
    ("ix_alerts_project_id_created_at", "alerts", "project_id, created_at DESC, id DESC"),
)

# 발송 대기 알림을 집는 쿼리(FOR UPDATE SKIP LOCKED)는 PENDING만 본다.
# 부분 인덱스면 발송이 끝난 알림이 아무리 쌓여도 인덱스가 커지지 않는다.
PENDING_ALERTS_INDEX = "ix_alerts_pending_created_at"


def upgrade() -> None:
    for index_name, table_name, columns in LIST_INDEXES:
        op.execute(f"CREATE INDEX {index_name} ON {table_name} ({columns})")

    op.create_index(
        PENDING_ALERTS_INDEX,
        "alerts",
        ["created_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(PENDING_ALERTS_INDEX, table_name="alerts")
    for index_name, table_name, _columns in reversed(LIST_INDEXES):
        op.drop_index(index_name, table_name=table_name)
