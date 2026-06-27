from uuid import UUID

from aim_api.database import SessionLocal
from aim_api.models.check_run import CheckRunStatus
from aim_api.models.project import Project
from aim_api.services import artifacts as artifact_service
from aim_api.services import check_runs as check_run_service
from aim_api.services import run_comparisons as run_comparison_service
from aim_api.services import scanner_results as scanner_result_service
from aim_api.services import score_results as score_result_service
from aim_api.services.scan_queue import RUN_CHECK_RUN_TASK_NAME

from aim_worker.artifacts import store_json_artifact
from aim_worker.availability import scan_http_availability
from aim_worker.celery_app import celery_app
from aim_worker.lighthouse import run_lighthouse_scan
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
