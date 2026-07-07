from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.user import User
from aim_api.schemas.ai_diagnosis import AIReportRead
from aim_api.schemas.check_run import (
    AIReportSummaryRead,
    ArtifactRead,
    AvailabilityResultRead,
    BaselineComparisonRead,
    CheckRunCreate,
    CheckRunDetailRead,
    CheckRunListItemRead,
    CheckRunRead,
    CheckRunScoreSummaryRead,
    LighthouseResultRead,
    RunComparisonRead,
    ScoreResultRead,
    SslResultRead,
)
from aim_api.schemas.scenario import ScenarioRunRead
from aim_api.services import ai_reports as ai_report_service
from aim_api.services import artifacts as artifact_service
from aim_api.services import check_runs as check_run_service
from aim_api.services import projects as project_service
from aim_api.services import run_comparisons as run_comparison_service
from aim_api.services import scan_queue
from aim_api.services import scanner_results as scanner_result_service
from aim_api.services import scenarios as scenario_service
from aim_api.services import score_results as score_result_service

router = APIRouter(prefix="/projects/{project_id}/check-runs", tags=["check-runs"])


def check_run_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Check run not found.",
    )


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def project_not_verified() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Project must be verified before creating a check run.",
    )


def ai_report_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="AI report not found.",
    )


def baseline_not_configured() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="No baseline check run is configured for this project.",
    )


def baseline_check_run_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Baseline check run not found.",
    )


def baseline_comparison_not_available() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Baseline comparison requires score results for both check runs.",
    )


def scan_queue_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Scan queue is unavailable.",
    )


def require_check_run_for_user(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    check_run_id: UUID,
) -> CheckRunRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=owner_id,
            project_id=project_id,
        )
        check_run = check_run_service.get_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise check_run_not_found() from exc

    return CheckRunRead.model_validate(check_run)


@router.post("", response_model=CheckRunRead, status_code=status.HTTP_201_CREATED)
def create_check_run(
    project_id: UUID,
    payload: CheckRunCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CheckRunRead:
    _ = payload
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.create_check_run(
            session,
            project=project,
            requested_by_id=current_user.id,
        )
        scenario_runs = scenario_service.create_scenario_runs_for_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run.id,
            requested_by_id=current_user.id,
        )
        scan_queue.enqueue_check_run(check_run_id=check_run.id)
        for scenario_run in scenario_runs:
            scan_queue.enqueue_scenario_run(scenario_run_id=scenario_run.id)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.ProjectNotVerifiedError as exc:
        raise project_not_verified() from exc
    except scan_queue.ScanQueueUnavailableError as exc:
        check_run_service.mark_check_run_failed(
            session,
            check_run_id=check_run.id,
            failure_reason="Scan queue is unavailable.",
        )
        for scenario_run in scenario_service.list_scenario_runs_for_check_run(
            session,
            check_run_id=check_run.id,
        ):
            scenario_service.mark_scenario_run_failed(
                session,
                scenario_run_id=scenario_run.id,
                failure_reason="Scan queue is unavailable.",
            )
        raise scan_queue_unavailable() from exc

    return CheckRunRead.model_validate(check_run)


@router.get("", response_model=list[CheckRunListItemRead])
def list_check_runs(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CheckRunListItemRead]:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    check_runs = check_run_service.list_check_runs(
        session,
        project_id=project.id,
        limit=limit,
        offset=offset,
    )
    check_run_ids = [check_run.id for check_run in check_runs]
    score_results = score_result_service.list_score_results_for_check_runs(
        session,
        check_run_ids=check_run_ids,
    )
    scenario_runs_by_check_run = scenario_service.list_scenario_runs_for_check_runs(
        session,
        check_run_ids=check_run_ids,
    )

    items: list[CheckRunListItemRead] = []
    for check_run in check_runs:
        item = CheckRunListItemRead.model_validate(check_run)
        score_result = score_results.get(check_run.id)
        if score_result is not None:
            item.score = CheckRunScoreSummaryRead.model_validate(score_result)
        item.linked_scenario_runs = [
            ScenarioRunRead.model_validate(scenario_run)
            for scenario_run in scenario_runs_by_check_run.get(check_run.id, [])
        ]
        items.append(item)
    return items


@router.get("/{check_run_id}", response_model=CheckRunDetailRead)
def get_check_run(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CheckRunDetailRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.get_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise check_run_not_found() from exc

    availability_result = scanner_result_service.get_availability_result(
        session,
        check_run_id=check_run.id,
    )
    ssl_result = scanner_result_service.get_ssl_result(
        session,
        check_run_id=check_run.id,
    )
    lighthouse_result = scanner_result_service.get_lighthouse_result(
        session,
        check_run_id=check_run.id,
    )
    artifacts = artifact_service.list_artifacts(
        session,
        check_run_id=check_run.id,
    )
    score_result = score_result_service.get_score_result(
        session,
        check_run_id=check_run.id,
    )
    comparison_result = run_comparison_service.get_run_comparison(
        session,
        check_run_id=check_run.id,
    )
    ai_report = ai_report_service.get_ai_report_or_none(
        session,
        check_run_id=check_run.id,
    )
    linked_scenario_runs = scenario_service.list_scenario_runs_for_check_run(
        session,
        check_run_id=check_run.id,
    )
    check_run_body = CheckRunRead.model_validate(check_run).model_dump()
    return CheckRunDetailRead(
        **check_run_body,
        availability_result=AvailabilityResultRead.model_validate(availability_result)
        if availability_result is not None
        else None,
        ssl_result=SslResultRead.model_validate(ssl_result) if ssl_result is not None else None,
        lighthouse_result=LighthouseResultRead.model_validate(lighthouse_result)
        if lighthouse_result is not None
        else None,
        score_result=ScoreResultRead.model_validate(score_result)
        if score_result is not None
        else None,
        comparison_result=RunComparisonRead.model_validate(comparison_result)
        if comparison_result is not None
        else None,
        ai_report=AIReportSummaryRead.model_validate(ai_report) if ai_report is not None else None,
        artifacts=[ArtifactRead.model_validate(artifact) for artifact in artifacts],
        linked_scenario_runs=[
            ScenarioRunRead.model_validate(scenario_run) for scenario_run in linked_scenario_runs
        ],
    )


@router.get("/{check_run_id}/baseline-comparison", response_model=BaselineComparisonRead)
def get_baseline_comparison(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    baseline_check_run_id: Annotated[UUID | None, Query()] = None,
) -> BaselineComparisonRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.get_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
        comparison = run_comparison_service.compute_baseline_comparison(
            session,
            project=project,
            check_run=check_run,
            baseline_check_run_id=baseline_check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise check_run_not_found() from exc
    except run_comparison_service.BaselineNotConfiguredError as exc:
        raise baseline_not_configured() from exc
    except run_comparison_service.BaselineCheckRunMissingError as exc:
        raise baseline_check_run_not_found() from exc
    except run_comparison_service.BaselineComparisonNotAvailableError as exc:
        raise baseline_comparison_not_available() from exc

    return BaselineComparisonRead.model_validate(comparison)


@router.get("/{check_run_id}/ai-report", response_model=AIReportRead)
def get_check_run_ai_report(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AIReportRead:
    check_run = require_check_run_for_user(
        session,
        owner_id=current_user.id,
        project_id=project_id,
        check_run_id=check_run_id,
    )
    try:
        ai_report = ai_report_service.get_ai_report(
            session,
            check_run_id=check_run.id,
        )
    except ai_report_service.AIReportNotFoundError as exc:
        raise ai_report_not_found() from exc

    return AIReportRead.model_validate(ai_report)


@router.post("/{check_run_id}/cancel", response_model=CheckRunRead)
def cancel_check_run(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CheckRunRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.cancel_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise check_run_not_found() from exc

    return CheckRunRead.model_validate(check_run)
