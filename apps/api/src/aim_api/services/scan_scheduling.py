from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project

SCHEDULED_TRIGGER_SOURCE = "scheduled"

# 정기 스캔 스케줄러의 advisory lock 키. 임의의 상수이며, 같은 데이터베이스에서
# 다른 용도로 재사용하지 않기만 하면 된다.
SCHEDULER_ADVISORY_LOCK_KEY = 8_413_207_001

ACTIVE_CHECK_RUN_STATUSES = (
    CheckRunStatus.QUEUED.value,
    CheckRunStatus.RUNNING.value,
    CheckRunStatus.ANALYZING.value,
)


@contextmanager
def scheduler_lock(session: Session) -> Iterator[bool]:
    """정기 스캔 스케줄링을 한 번에 하나만 돌게 만든다.

    "만료된 프로젝트를 읽고 → 검사를 만든다"는 read-then-write라, beat가 둘이면
    같은 프로젝트에 검사가 두 개 생긴다. 지금까지 무사했던 이유는 코드가 아니라
    "beat 1개"라는 배포 형상뿐이었다.

    pg_try_advisory_lock은 기다리지 않고 즉시 실패를 알려준다 — 스케줄러는
    주기적으로 다시 도니까, 잠금을 못 얻으면 이번 회차를 건너뛰는 것이 맞다.
    잠금은 세션 단위라 끝나고 반드시 푼다.
    """
    acquired = bool(
        session.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": SCHEDULER_ADVISORY_LOCK_KEY},
        )
    )

    try:
        yield acquired
    finally:
        if acquired:
            session.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": SCHEDULER_ADVISORY_LOCK_KEY},
            )
            session.commit()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def get_latest_check_run_created_at_by_project(session: Session) -> dict[UUID, datetime]:
    statement = select(CheckRun.project_id, func.max(CheckRun.created_at)).group_by(
        CheckRun.project_id
    )
    return {project_id: created_at for project_id, created_at in session.execute(statement)}


def get_project_ids_with_active_check_run(session: Session) -> set[UUID]:
    statement = (
        select(CheckRun.project_id).where(CheckRun.status.in_(ACTIVE_CHECK_RUN_STATUSES)).distinct()
    )
    return set(session.scalars(statement))


def is_project_due(
    project: Project,
    *,
    now: datetime,
    latest_check_run_created_at: datetime | None,
) -> bool:
    if latest_check_run_created_at is None:
        return True

    next_due_at = as_utc(latest_check_run_created_at) + timedelta(
        minutes=project.scan_interval_minutes
    )
    return next_due_at <= as_utc(now)


def list_due_projects(session: Session, *, now: datetime | None = None) -> list[Project]:
    """Return opted-in verified projects whose scan interval has elapsed with no active run."""
    current_time = now or datetime.now(UTC)
    statement = select(Project).where(
        Project.verified_at.is_not(None),
        Project.owner_id.is_not(None),
        Project.scheduled_scans_enabled.is_(True),
    )
    verified_projects = list(session.scalars(statement))
    if not verified_projects:
        return []

    latest_run_at_by_project = get_latest_check_run_created_at_by_project(session)
    active_project_ids = get_project_ids_with_active_check_run(session)

    return [
        project
        for project in verified_projects
        if project.id not in active_project_ids
        and is_project_due(
            project,
            now=current_time,
            latest_check_run_created_at=latest_run_at_by_project.get(project.id),
        )
    ]


def create_scheduled_check_run(session: Session, *, project: Project) -> CheckRun:
    if project.owner_id is None:
        raise ValueError("Cannot create a scheduled check run without a project owner.")

    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=CheckRunStatus.QUEUED.value,
        trigger_source=SCHEDULED_TRIGGER_SOURCE,
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run
