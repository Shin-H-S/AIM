from uuid import UUID

from aim_api.database import SessionLocal
from aim_api.models.check_run import CheckRunStatus
from aim_api.services import check_runs as check_run_service
from aim_api.services.scan_queue import RUN_CHECK_RUN_TASK_NAME

from aim_worker.celery_app import celery_app

SCANNER_NOT_IMPLEMENTED_REASON = "HTTP availability scanner is not implemented yet."
SCAN_WORKER_FAILED_REASON = "Scan worker failed."


class ScanExecutionNotImplementedError(Exception):
    """Raised until the first real scanner is implemented."""


def execute_scan_placeholder() -> None:
    raise ScanExecutionNotImplementedError(SCANNER_NOT_IMPLEMENTED_REASON)


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

        try:
            execute_scan_placeholder()
        except ScanExecutionNotImplementedError as exc:
            check_run_service.mark_check_run_failed(
                session,
                check_run_id=parsed_check_run_id,
                failure_reason=str(exc),
            )
        except Exception:
            check_run_service.mark_check_run_failed(
                session,
                check_run_id=parsed_check_run_id,
                failure_reason=SCAN_WORKER_FAILED_REASON,
            )
            raise
