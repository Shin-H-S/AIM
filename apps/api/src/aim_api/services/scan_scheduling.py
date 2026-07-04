from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project

SCHEDULED_TRIGGER_SOURCE = "scheduled"

ACTIVE_CHECK_RUN_STATUSES = (
    CheckRunStatus.QUEUED.value,
    CheckRunStatus.RUNNING.value,
    CheckRunStatus.ANALYZING.value,
)


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
    """Return verified projects whose scan interval has elapsed and have no active run."""
    current_time = now or datetime.now(UTC)
    statement = select(Project).where(
        Project.verified_at.is_not(None),
        Project.owner_id.is_not(None),
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
