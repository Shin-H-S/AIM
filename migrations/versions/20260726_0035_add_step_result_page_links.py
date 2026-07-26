"""Add page_links evidence to step results.

Revision ID: 20260726_0035
Revises: 20260724_0034
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0035"
down_revision: str | Sequence[str] | None = "20260724_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 실패 시점 페이지에 남아 있던 내부 링크. 기대 요소가 이사했는지(시나리오 스테일)
    # 흔적 없이 사라졌는지(UI 회귀)를 가르는 단서라, 조사 에이전트가 읽는다.
    # nullable로 둔다 — NULL은 '수집 이전 데이터', 빈 배열은 '수집했지만 링크 없음'.
    op.add_column("step_results", sa.Column("page_links", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("step_results", "page_links")
