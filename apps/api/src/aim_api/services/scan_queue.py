from uuid import UUID

from celery import Celery

from aim_api.config import get_settings

RUN_CHECK_RUN_TASK_NAME = "aim_worker.run_check_run"
RUN_SCENARIO_RUN_TASK_NAME = "aim_worker.run_scenario_run"
RUN_AI_REPORT_TASK_NAME = "aim_worker.generate_ai_report"
DELIVER_EMAIL_ALERTS_TASK_NAME = "aim_worker.deliver_pending_email_alerts"
SCHEDULE_CHECK_RUNS_TASK_NAME = "aim_worker.schedule_due_check_runs"
RUN_AGENT_INVESTIGATION_TASK_NAME = "aim_worker.run_agent_investigation"


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


def enqueue_ai_report(*, check_run_id: UUID) -> str:
    task_id = f"ai-report:{check_run_id}"
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            RUN_AI_REPORT_TASK_NAME,
            args=[str(check_run_id)],
            task_id=task_id,
        )
    except Exception as exc:
        raise ScanQueueUnavailableError from exc

    return str(result.id)


def enqueue_agent_investigation(*, check_run_id: UUID, incident_id: UUID | None = None) -> str:
    # task_id를 검사 단위로 고정해 같은 검사에 대한 중복 조사 큐잉을 막는다.
    task_id = f"agent-investigation:{check_run_id}"
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            RUN_AGENT_INVESTIGATION_TASK_NAME,
            args=[str(check_run_id), str(incident_id) if incident_id else None],
            task_id=task_id,
        )
    except Exception as exc:
        raise ScanQueueUnavailableError from exc

    return str(result.id)


def enqueue_email_alert_delivery(*, check_run_id: UUID) -> str:
    task_id = f"email-alerts:{check_run_id}"
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            DELIVER_EMAIL_ALERTS_TASK_NAME,
            task_id=task_id,
        )
    except Exception as exc:
        raise ScanQueueUnavailableError from exc

    return str(result.id)


def enqueue_email_alert_retry(*, alert_id: UUID) -> str:
    task_id = f"email-alert-retry:{alert_id}"
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            DELIVER_EMAIL_ALERTS_TASK_NAME,
            task_id=task_id,
        )
    except Exception as exc:
        raise ScanQueueUnavailableError from exc

    return str(result.id)
