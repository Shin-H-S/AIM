from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.project import Project
from aim_api.schemas.project import ProjectCreate, ProjectUpdate
from aim_api.url_validation import validate_service_url


class ProjectNotFoundError(Exception):
    """Raised when a project does not exist."""


def create_project(session: Session, *, owner_id: UUID, payload: ProjectCreate) -> Project:
    validate_service_url(str(payload.service_url))
    project = Project(
        owner_id=owner_id,
        name=payload.name,
        service_url=str(payload.service_url),
        description=payload.description,
        environment=payload.environment.value,
        scan_interval_minutes=payload.scan_interval_minutes,
        response_time_threshold_ms=payload.response_time_threshold_ms,
        quality_score_threshold=payload.quality_score_threshold,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def list_projects(session: Session, *, owner_id: UUID, limit: int, offset: int) -> list[Project]:
    statement = (
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_project(session: Session, *, owner_id: UUID, project_id: UUID) -> Project:
    statement = select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    project = session.scalar(statement)
    if project is None:
        raise ProjectNotFoundError

    return project


def update_project(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    payload: ProjectUpdate,
) -> Project:
    project = get_project(session, owner_id=owner_id, project_id=project_id)
    updated_fields = payload.model_fields_set

    if "name" in updated_fields and payload.name is not None:
        project.name = payload.name
    if "service_url" in updated_fields and payload.service_url is not None:
        validate_service_url(str(payload.service_url))
        project.service_url = str(payload.service_url)
    if "description" in updated_fields:
        project.description = payload.description
    if "environment" in updated_fields and payload.environment is not None:
        project.environment = payload.environment.value
    if "scan_interval_minutes" in updated_fields and payload.scan_interval_minutes is not None:
        project.scan_interval_minutes = payload.scan_interval_minutes
    if (
        "response_time_threshold_ms" in updated_fields
        and payload.response_time_threshold_ms is not None
    ):
        project.response_time_threshold_ms = payload.response_time_threshold_ms
    if "quality_score_threshold" in updated_fields and payload.quality_score_threshold is not None:
        project.quality_score_threshold = payload.quality_score_threshold

    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, *, owner_id: UUID, project_id: UUID) -> None:
    project = get_project(session, owner_id=owner_id, project_id=project_id)
    session.delete(project)
    session.commit()
