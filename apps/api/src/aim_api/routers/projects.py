from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.schemas.project import (
    ProjectBaselineUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectVerificationRead,
    ProjectVerificationResult,
)
from aim_api.services import domain_verification
from aim_api.services import projects as project_service
from aim_api.url_validation import UrlValidationError

router = APIRouter(prefix="/projects", tags=["projects"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def unsafe_service_url() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Service URL is not allowed.",
    )


def baseline_check_run_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Check run not found.",
    )


def baseline_check_run_not_comparable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Check run must be terminal and scored to be used as a baseline.",
    )


def domain_verification_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Domain verification failed.",
    )


def build_verification_response(project: Project) -> ProjectVerificationRead:
    verification_token = domain_verification.require_verification_token(project)
    return ProjectVerificationRead(
        project_id=project.id,
        verification_token=verification_token,
        meta_tag=domain_verification.build_meta_tag(project),
        is_verified=project.is_verified,
        verified_at=project.verified_at,
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    try:
        project = project_service.create_project(session, owner_id=current_user.id, payload=payload)
    except UrlValidationError as exc:
        raise unsafe_service_url() from exc

    return ProjectRead.model_validate(project)


@router.get("/{project_id}/verification", response_model=ProjectVerificationRead)
def get_project_verification(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectVerificationRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    project = domain_verification.ensure_verification_token(session, project)
    return build_verification_response(project)


@router.post("/{project_id}/verify", response_model=ProjectVerificationResult)
def verify_project_domain(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectVerificationResult:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        project = domain_verification.verify_project_domain(session, project)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except (domain_verification.DomainVerificationError, UrlValidationError) as exc:
        raise domain_verification_failed() from exc

    response = build_verification_response(project)
    return ProjectVerificationResult(**response.model_dump(), status="verified")


@router.get("", response_model=list[ProjectRead])
def list_projects(
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProjectRead]:
    projects = project_service.list_projects(
        session,
        owner_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    try:
        project = project_service.update_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
            payload=payload,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except UrlValidationError as exc:
        raise unsafe_service_url() from exc

    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        project_service.delete_project(session, owner_id=current_user.id, project_id=project_id)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{project_id}/baseline", response_model=ProjectRead)
def set_project_baseline(
    project_id: UUID,
    payload: ProjectBaselineUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        project = project_service.set_baseline_check_run(
            session,
            project=project,
            check_run_id=payload.check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except project_service.BaselineCheckRunNotFoundError as exc:
        raise baseline_check_run_not_found() from exc
    except project_service.BaselineCheckRunNotComparableError as exc:
        raise baseline_check_run_not_comparable() from exc

    return ProjectRead.model_validate(project)


@router.delete("/{project_id}/baseline", response_model=ProjectRead)
def clear_project_baseline(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    project = project_service.clear_baseline_check_run(session, project=project)
    return ProjectRead.model_validate(project)
