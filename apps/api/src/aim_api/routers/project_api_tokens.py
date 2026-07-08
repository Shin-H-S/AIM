from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.user import User
from aim_api.schemas.project_api_token import (
    ProjectApiTokenCreate,
    ProjectApiTokenIssuedRead,
    ProjectApiTokenRead,
)
from aim_api.services import project_api_tokens as token_service
from aim_api.services import projects as project_service

router = APIRouter(prefix="/projects/{project_id}/tokens", tags=["project-api-tokens"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def token_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project API token not found.",
    )


@router.post("", response_model=ProjectApiTokenIssuedRead, status_code=status.HTTP_201_CREATED)
def create_project_api_token(
    project_id: UUID,
    payload: ProjectApiTokenCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectApiTokenIssuedRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    issued = token_service.issue_token(session, project_id=project.id, name=payload.name)
    read = ProjectApiTokenRead.model_validate(issued.record)
    return ProjectApiTokenIssuedRead(**read.model_dump(), token=issued.plaintext)


@router.get("", response_model=list[ProjectApiTokenRead])
def list_project_api_tokens(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectApiTokenRead]:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    tokens = token_service.list_tokens(session, project_id=project.id)
    return [ProjectApiTokenRead.model_validate(token) for token in tokens]


@router.delete("/{token_id}", response_model=ProjectApiTokenRead)
def revoke_project_api_token(
    project_id: UUID,
    token_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectApiTokenRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        token = token_service.revoke_token(
            session,
            project_id=project.id,
            token_id=token_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except token_service.ProjectApiTokenNotFoundError as exc:
        raise token_not_found() from exc

    return ProjectApiTokenRead.model_validate(token)
