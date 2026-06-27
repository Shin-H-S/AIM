from uuid import UUID

from celery import Celery

from aim_api.config import get_settings

RUN_CHECK_RUN_TASK_NAME = "aim_worker.run_check_run"
RUN_SCENARIO_RUN_TASK_NAME = "aim_worker.run_scenario_run"


class ScanQueueUnavailableError(Exception):
    """Raised when a check run cannot be submitted to the scan queue."""


def build_celery_client() -> Celery:
    settings = get_settings()
    return Celery(
        "aim-api",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )


def enqueue_check_run(*, check_run_id: UUID) -> str:
    task_id = str(check_run_id)
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            RUN_CHECK_RUN_TASK_NAME,
            args=[task_id],
            task_id=task_id,
        )
    except Exception as exc:
        raise ScanQueueUnavailableError from exc

    return str(result.id)


def enqueue_scenario_run(*, scenario_run_id: UUID) -> str:
    task_id = str(scenario_run_id)
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            RUN_SCENARIO_RUN_TASK_NAME,
            args=[task_id],
            task_id=task_id,
        )
    except Exception as exc:
        raise ScanQueueUnavailableError from exc

    return str(result.id)
