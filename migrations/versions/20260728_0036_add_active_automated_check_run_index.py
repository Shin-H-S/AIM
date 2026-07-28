"""Add a partial unique index for active automated check runs.

Revision ID: 20260728_0036
Revises: 20260726_0035
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0036"
down_revision: str | Sequence[str] | None = "20260726_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_check_runs_one_active_automated_per_project"
ACTIVE_AUTOMATED_CHECK_RUN_CONDITION = (
    "status IN ('QUEUED', 'RUNNING', 'ANALYZING') AND trigger_source IN ('scheduled', 'deploy')"
)


def upgrade() -> None:
    # 자동 트리거(정기 스캔·배포 훅) 검사는 프로젝트당 하나만 활성일 수 있다.
    # 두 경로 모두 애플리케이션에서 활성 검사를 확인하지만 그건 check-then-act라,
    # 배포 훅이 동시에 두 번 들어오면 둘 다 통과해 큐가 쌓인다. 최후 방어선을
    # 데이터베이스에 둔다.
    #
    # 수동 검사와 에이전트 재검사는 일부러 제외한다 — 사용자가 검사 중에 다시
    # 실행하거나, 정기 검사 도중 조사 재검사가 뜨는 것은 정상 동작이다.
    #
    # 주의: 이 마이그레이션은 같은 프로젝트에 활성 자동 검사가 이미 둘 이상 있으면
    # 실패한다(워커가 죽어 QUEUED로 굳은 검사 등). 사전 확인:
    #   SELECT project_id, count(*) FROM check_runs
    #    WHERE status IN ('QUEUED','RUNNING','ANALYZING')
    #      AND trigger_source IN ('scheduled','deploy')
    #    GROUP BY project_id HAVING count(*) > 1;
    op.create_index(
        INDEX_NAME,
        "check_runs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_AUTOMATED_CHECK_RUN_CONDITION),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="check_runs")
