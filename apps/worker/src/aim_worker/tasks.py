from uuid import UUID

from aim_api.database import SessionLocal
from aim_api.models.check_run import CheckRunStatus
from aim_api.models.project import Project
from aim_api.services import check_runs as check_run_service
from aim_api.services.scan_queue import RUN_CHECK_RUN_TASK_NAME

from aim_worker.availability import scan_http_availability
from aim_worker.celery_app import celery_app
from aim_worker.ssl_inspection import inspect_ssl_certificate

SCAN_WORKER_FAILED_REASON = "Scan worker failed."
CHECK_RUN_PROJECT_NOT_FOUND_REASON = "Project for check run was not found."


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

        if availability_result.is_available:
            ssl_result = inspect_ssl_certificate(
                availability_result.final_url or project.service_url,
            )
            if ssl_result.is_applicable and ssl_result.is_valid is False:
                check_run_service.mark_check_run_failed(
                    session,
                    check_run_id=parsed_check_run_id,
                    failure_reason=ssl_result.failure_reason or "SSL certificate is invalid.",
                )
                return

            check_run_service.mark_check_run_completed(
                session,
                check_run_id=parsed_check_run_id,
            )
            return

        failure_reason = availability_result.failure_reason or "Service is unavailable."
        check_run_service.mark_check_run_failed(
            session,
            check_run_id=parsed_check_run_id,
            failure_reason=failure_reason,
        )
