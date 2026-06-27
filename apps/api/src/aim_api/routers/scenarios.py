from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.scenario import TestScenario
from aim_api.models.user import User
from aim_api.schemas.scenario import (
    TestScenarioCreate,
    TestScenarioRead,
    TestScenarioUpdate,
    TestStepRead,
)
from aim_api.services import projects as project_service
from aim_api.services import scenarios as scenario_service

router = APIRouter(prefix="/projects/{project_id}/scenarios", tags=["scenarios"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def scenario_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Test scenario not found.",
    )


def build_scenario_response(session: Session, scenario: TestScenario) -> TestScenarioRead:
    steps = scenario_service.list_steps(session, scenario_id=scenario.id)
    scenario_body = TestScenarioRead.model_validate(
        {
            "id": scenario.id,
            "project_id": scenario.project_id,
            "name": scenario.name,
            "description": scenario.description,
            "is_active": scenario.is_active,
            "steps": [TestStepRead.model_validate(step) for step in steps],
            "created_at": scenario.created_at,
            "updated_at": scenario.updated_at,
        }
    )
    return scenario_body


@router.post("", response_model=TestScenarioRead, status_code=status.HTTP_201_CREATED)
def create_scenario(
    project_id: UUID,
    payload: TestScenarioCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestScenarioRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    scenario = scenario_service.create_scenario(
        session,
        project_id=project.id,
        payload=payload,
    )
    return build_scenario_response(session, scenario)


@router.get("", response_model=list[TestScenarioRead])
def list_scenarios(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TestScenarioRead]:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    scenarios = scenario_service.list_scenarios(
        session,
        project_id=project.id,
        limit=limit,
        offset=offset,
    )
    return [build_scenario_response(session, scenario) for scenario in scenarios]


@router.get("/{scenario_id}", response_model=TestScenarioRead)
def get_scenario(
    project_id: UUID,
    scenario_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestScenarioRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        scenario = scenario_service.get_scenario(
            session,
            project_id=project.id,
            scenario_id=scenario_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except scenario_service.TestScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    return build_scenario_response(session, scenario)


@router.patch("/{scenario_id}", response_model=TestScenarioRead)
def update_scenario(
    project_id: UUID,
    scenario_id: UUID,
    payload: TestScenarioUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestScenarioRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        scenario = scenario_service.update_scenario(
            session,
            project_id=project.id,
            scenario_id=scenario_id,
            payload=payload,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except scenario_service.TestScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    return build_scenario_response(session, scenario)


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    project_id: UUID,
    scenario_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        scenario_service.delete_scenario(
            session,
            project_id=project.id,
            scenario_id=scenario_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except scenario_service.TestScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
