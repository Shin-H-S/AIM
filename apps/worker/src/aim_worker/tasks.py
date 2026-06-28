import logging
from uuid import UUID

from aim_api.database import SessionLocal
from aim_api.models.check_run import CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus
from aim_api.services import artifacts as artifact_service
from aim_api.services import check_runs as check_run_service
from aim_api.services import run_comparisons as run_comparison_service
from aim_api.services import scanner_results as scanner_result_service
from aim_api.services import scenarios as scenario_service
from aim_api.services import score_results as score_result_service
from aim_api.services.scan_queue import RUN_CHECK_RUN_TASK_NAME, RUN_SCENARIO_RUN_TASK_NAME
from sqlalchemy.orm import Session

from aim_worker.artifacts import StoredArtifact, store_binary_artifact, store_json_artifact
from aim_worker.availability import scan_http_availability
from aim_worker.celery_app import celery_app
from aim_worker.lighthouse import run_lighthouse_scan
from aim_worker.playwright_runner import run_playwright_scenario
from aim_worker.ssl_inspection import inspect_ssl_certificate

SCAN_WORKER_FAILED_REASON = "Scan worker failed."
CHECK_RUN_PROJECT_NOT_FOUND_REASON = "Project for check run was not found."
SCENARIO_WORKER_FAILED_REASON = "Scenario worker failed."
logger = logging.getLogger(__name__)


def store_failure_screenshot_artifact(
    *,
    scenario_run_id: UUID,
    step_order: int,
    payload: bytes | None,
) -> StoredArtifact | None:
    if payload is None:
        return None

    storage_path = f"scenario-runs/{scenario_run_id}/steps/{step_order}/failure.png"
    return store_binary_artifact(
        artifact_type="scenario_failure_screenshot",
        storage_path=storage_path,
        content_type="image/png",
        payload=payload,
    )


def refresh_linked_check_run_score(session: Session, *, scenario_run: ScenarioRun) -> None:
    if scenario_run.check_run_id is None:
        return

    try:
        check_run = check_run_service.get_check_run_by_id(
            session,
            check_run_id=scenario_run.check_run_id,
        )
    except check_run_service.CheckRunNotFoundError:
        return

    project = session.get(Project, check_run.project_id)
    if project is None:
        return

    availability_result = scanner_result_service.get_availability_result(
        session,
        check_run_id=check_run.id,
    )
    if availability_result is None:
        return

    ssl_result = scanner_result_service.get_ssl_result(
        session,
        check_run_id=check_run.id,
    )
    lighthouse_result = scanner_result_service.get_lighthouse_result(
        session,
        check_run_id=check_run.id,
    )
    score_result = score_result_service.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
    )
    run_comparison_service.record_previous_run_comparison(
        session,
        check_run=check_run,
        current_score_result=score_result,
        current_availability_result=availability_result,
        current_lighthouse_result=lighthouse_result,
    )


@celery_app.task(  # type: ignore[untyped-decorator]
    name=RUN_SCENARIO_RUN_TASK_NAME,
    soft_time_limit=180,
    time_limit=240,
)
def run_scenario_run(scenario_run_id: str) -> None:
    parsed_scenario_run_id = UUID(scenario_run_id)
    with SessionLocal() as session:
        try:
            scenario_run = scenario_service.mark_scenario_run_running(
                session,
                scenario_run_id=parsed_scenario_run_id,
            )
        except scenario_service.ScenarioRunNotFoundError:
            return

        if scenario_run.status != ScenarioRunStatus.RUNNING.value:
            return

        steps = scenario_service.list_steps(session, scenario_id=scenario_run.scenario_id)
        scenario_service.clear_step_results(
            session,
            scenario_run_id=parsed_scenario_run_id,
        )
        scenario_service.clear_failure_evidence(
            session,
            scenario_run_id=parsed_scenario_run_id,
        )
        try:
            execution_result = run_playwright_scenario(steps)
        except Exception:
            scenario_service.mark_scenario_run_failed(
                session,
                scenario_run_id=parsed_scenario_run_id,
                failure_reason=SCENARIO_WORKER_FAILED_REASON,
            )
            raise

        for step_result in execution_result.step_results:
            failure_screenshot_artifact_id = None
            try:
                stored_screenshot = store_failure_screenshot_artifact(
                    scenario_run_id=parsed_scenario_run_id,
                    step_order=step_result.step_order,
                    payload=step_result.failure_screenshot,
                )
                if stored_screenshot is not None:
                    screenshot_artifact = artifact_service.record_artifact(
                        session,
                        scenario_run_id=parsed_scenario_run_id,
                        artifact_type=stored_screenshot.artifact_type,
                        storage_backend=stored_screenshot.storage_backend,
                        storage_path=stored_screenshot.storage_path,
                        content_type=stored_screenshot.content_type,
                        size_bytes=stored_screenshot.size_bytes,
                        checksum_sha256=stored_screenshot.checksum_sha256,
                    )
                    failure_screenshot_artifact_id = screenshot_artifact.id
            except Exception:
                logger.exception(
                    "Failed to store scenario failure screenshot.",
                    extra={
                        "scenario_run_id": str(parsed_scenario_run_id),
                        "step_order": step_result.step_order,
                    },
                )

            scenario_service.record_step_result(
                session,
                scenario_run_id=parsed_scenario_run_id,
                test_step_id=step_result.test_step_id,
                step_order=step_result.step_order,
                action=step_result.action,
                target=step_result.target,
                status=step_result.status,
                started_at=step_result.started_at,
                finished_at=step_result.finished_at,
                duration_ms=step_result.duration_ms,
                error_message=step_result.error_message,
                failure_screenshot_artifact_id=failure_screenshot_artifact_id,
            )

        for console_error in execution_result.console_errors:
            scenario_service.record_console_error(
                session,
                scenario_run_id=parsed_scenario_run_id,
                level=console_error.level,
                message=console_error.message,
                source_url=console_error.source_url,
                line_number=console_error.line_number,
                column_number=console_error.column_number,
            )

        for network_failure in execution_result.network_failures:
            scenario_service.record_network_failure(
                session,
                scenario_run_id=parsed_scenario_run_id,
                request_url=network_failure.request_url,
                method=network_failure.method,
                resource_type=network_failure.resource_type,
                failure_text=network_failure.failure_text,
            )

        if execution_result.is_successful:
            completed_scenario_run = scenario_service.mark_scenario_run_completed(
                session,
                scenario_run_id=parsed_scenario_run_id,
            )
            refresh_linked_check_run_score(session, scenario_run=completed_scenario_run)
            return

        failed_scenario_run = scenario_service.mark_scenario_run_failed(
            session,
            scenario_run_id=parsed_scenario_run_id,
            failure_reason=execution_result.failure_reason or "Scenario failed.",
        )
        refresh_linked_check_run_score(session, scenario_run=failed_scenario_run)


@celery_app.task(  # type: ignore[untyped-decorator]
    name=RUN_CHECK_RUN_TASK_NAME,
    soft_time_limit=240,
    time_limit=300,
)
def run_check_run(check_run_id: str) -> None:
    parsed_check_run_id = UUID(check_run_id)
    with SessionLocal() as session:
        try:
            check_run = check_run_service.mark_check_run_running(
                session,
                check_run_id=parsed_check_run_id,
            )
        except check_run_service.CheckRunNotFoundError:
            return

        if check_run.status != CheckRunStatus.RUNNING.value:
            return

        project = session.get(Project, check_run.project_id)
        if project is None:
            check_run_service.mark_check_run_failed(
                session,
                check_run_id=parsed_check_run_id,
                failure_reason=CHECK_RUN_PROJECT_NOT_FOUND_REASON,
            )
            return

        try:
            availability_result = scan_http_availability(project.service_url)
        except Exception:
            check_run_service.mark_check_run_failed(
                session,
                check_run_id=parsed_check_run_id,
                failure_reason=SCAN_WORKER_FAILED_REASON,
            )
            raise

        saved_availability_result = scanner_result_service.record_availability_result(
            session,
            check_run_id=parsed_check_run_id,
            service_url=availability_result.service_url,
            final_url=availability_result.final_url,
            is_available=availability_result.is_available,
            status_code=availability_result.status_code,
            response_time_ms=availability_result.response_time_ms,
            redirect_count=availability_result.redirect_count,
            uses_https=availability_result.uses_https,
            timed_out=availability_result.timed_out,
            failure_reason=availability_result.failure_reason,
        )

        if availability_result.is_available:
            ssl_result = inspect_ssl_certificate(
                availability_result.final_url or project.service_url,
            )
            saved_ssl_result = scanner_result_service.record_ssl_result(
                session,
                check_run_id=parsed_check_run_id,
                service_url=ssl_result.service_url,
                is_applicable=ssl_result.is_applicable,
                is_valid=ssl_result.is_valid,
                expires_at=ssl_result.expires_at,
                days_until_expiration=ssl_result.days_until_expiration,
                failure_reason=ssl_result.failure_reason,
            )
            if ssl_result.is_applicable and ssl_result.is_valid is False:
                score_result = score_result_service.record_score_result(
                    session,
                    check_run_id=parsed_check_run_id,
                    project=project,
                    availability_result=saved_availability_result,
                    ssl_result=saved_ssl_result,
                    lighthouse_result=None,
                )
                run_comparison_service.record_previous_run_comparison(
                    session,
                    check_run=check_run,
                    current_score_result=score_result,
                    current_availability_result=saved_availability_result,
                    current_lighthouse_result=None,
                )
                check_run_service.mark_check_run_failed(
                    session,
                    check_run_id=parsed_check_run_id,
                    failure_reason=ssl_result.failure_reason or "SSL certificate is invalid.",
                )
                return

            check_run_service.mark_check_run_analyzing(
                session,
                check_run_id=parsed_check_run_id,
            )
            try:
                lighthouse_result = run_lighthouse_scan(
                    availability_result.final_url or project.service_url,
                )
                raw_json_artifact_id = None
                if lighthouse_result.raw_json is not None:
                    stored_artifact = store_json_artifact(
                        check_run_id=parsed_check_run_id,
                        artifact_type="lighthouse_raw_json",
                        payload=lighthouse_result.raw_json,
                        relative_path="lighthouse/raw.json",
                    )
                    raw_json_artifact = artifact_service.record_artifact(
                        session,
                        check_run_id=parsed_check_run_id,
                        artifact_type=stored_artifact.artifact_type,
                        storage_backend=stored_artifact.storage_backend,
                        storage_path=stored_artifact.storage_path,
                        content_type=stored_artifact.content_type,
                        size_bytes=stored_artifact.size_bytes,
                        checksum_sha256=stored_artifact.checksum_sha256,
                    )
                    raw_json_artifact_id = raw_json_artifact.id

                saved_lighthouse_result = scanner_result_service.record_lighthouse_result(
                    session,
                    check_run_id=parsed_check_run_id,
                    service_url=lighthouse_result.service_url,
                    is_successful=lighthouse_result.is_successful,
                    performance_score=lighthouse_result.performance_score,
                    accessibility_score=lighthouse_result.accessibility_score,
                    seo_score=lighthouse_result.seo_score,
                    best_practices_score=lighthouse_result.best_practices_score,
                    largest_contentful_paint_ms=lighthouse_result.largest_contentful_paint_ms,
                    cumulative_layout_shift=lighthouse_result.cumulative_layout_shift,
                    total_blocking_time_ms=lighthouse_result.total_blocking_time_ms,
                    raw_json_artifact_id=raw_json_artifact_id,
                    failure_reason=lighthouse_result.failure_reason,
                )
            except Exception:
                check_run_service.mark_check_run_failed(
                    session,
                    check_run_id=parsed_check_run_id,
                    failure_reason=SCAN_WORKER_FAILED_REASON,
                )
                raise

            score_result = score_result_service.record_score_result(
                session,
                check_run_id=parsed_check_run_id,
                project=project,
                availability_result=saved_availability_result,
                ssl_result=saved_ssl_result,
                lighthouse_result=saved_lighthouse_result,
            )
            run_comparison_service.record_previous_run_comparison(
                session,
                check_run=check_run,
                current_score_result=score_result,
                current_availability_result=saved_availability_result,
                current_lighthouse_result=saved_lighthouse_result,
            )
            if not lighthouse_result.is_successful:
                check_run_service.mark_check_run_failed(
                    session,
                    check_run_id=parsed_check_run_id,
                    failure_reason=lighthouse_result.failure_reason or "Lighthouse scan failed.",
                )
                return

            check_run_service.mark_check_run_completed(
                session,
                check_run_id=parsed_check_run_id,
            )
            return

        failure_reason = availability_result.failure_reason or "Service is unavailable."
        score_result = score_result_service.record_score_result(
            session,
            check_run_id=parsed_check_run_id,
            project=project,
            availability_result=saved_availability_result,
            ssl_result=None,
            lighthouse_result=None,
        )
        run_comparison_service.record_previous_run_comparison(
            session,
            check_run=check_run,
            current_score_result=score_result,
            current_availability_result=saved_availability_result,
            current_lighthouse_result=None,
        )
        check_run_service.mark_check_run_failed(
            session,
            check_run_id=parsed_check_run_id,
            failure_reason=failure_reason,
        )
