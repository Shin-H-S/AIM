from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from aim_api.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Annotated[Session, Depends(get_db)],
) -> ProjectRead:
    project = project_service.create_project(session, payload)
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProjectRead]:
    projects = project_service.list_projects(session, limit=limit, offset=offset)
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
) -> ProjectRead:
    try:
        project = project_service.get_project(session, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> ProjectRead:
    try:
        project = project_service.update_project(session, project_id, payload)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        project_service.delete_project(session, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
