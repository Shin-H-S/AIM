from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from aim_api.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class CheckRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CheckRun(Base):
    __tablename__ = "check_runs"
    __table_args__ = (
        Index(
            "ix_check_runs_project_id_created_at",
            "project_id",
            text("created_at DESC"),
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'ANALYZING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_check_runs_status",
        ),
        # 자동 트리거(정기 스캔·배포 훅) 검사는 프로젝트당 하나만 활성일 수 있다.
        # 애플리케이션 가드는 check-then-act라 동시 호출을 막지 못한다.
        # 수동 검사와 에이전트 재검사는 의도적으로 제외한다 — 검사 중 수동 실행과
        # 정기 검사 중 조사 재검사는 정상 동작이다.
        Index(
            "ix_check_runs_one_active_automated_per_project",
            "project_id",
            unique=True,
            postgresql_where=text(
                "status IN ('QUEUED', 'RUNNING', 'ANALYZING') "
                "AND trigger_source IN ('scheduled', 'deploy')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CheckRunStatus.QUEUED.value,
    )
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    # 배포 훅으로 생성된 검사가 어떤 배포(커밋 SHA·버전 등)의 결과인지 추적한다.
    deploy_ref: Mapped[str | None] = mapped_column(String(255))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
