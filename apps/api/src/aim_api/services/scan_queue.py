from uuid import UUID

from celery import Celery

from aim_api.config import get_settings

RUN_CHECK_RUN_TASK_NAME = "aim_worker.run_check_run"
RUN_SCENARIO_RUN_TASK_NAME = "aim_worker.run_scenario_run"
RUN_AI_REPORT_TASK_NAME = "aim_worker.generate_ai_report"
DELIVER_EMAIL_ALERTS_TASK_NAME = "aim_worker.deliver_pending_email_alerts"
SCHEDULE_CHECK_RUNS_TASK_NAME = "aim_worker.schedule_due_check_runs"
RUN_AGENT_INVESTIGATION_TASK_NAME = "aim_worker.run_agent_investigation"
PURGE_EXPIRED_ARTIFACTS_TASK_NAME = "aim_worker.purge_expired_artifacts"


# 큐 이름. 기본 큐는 Celery 기본값("celery")을 그대로 둔다 — 이름을 바꾸면
# 배포 시점에 이미 큐에 들어가 있던 메시지를 아무도 소비하지 않게 된다.
SCANS_QUEUE = "scans"
AGENT_QUEUE = "agent"

# 조사 에이전트를 별도 큐로 빼는 이유는 두 가지다.
#
# 1) 굶주림: run_agent_investigation은 슬롯을 최대 7분(soft 420s) 잡는다.
#    인시던트는 원래 몰려서 터지므로, 같은 큐에 두면 **가장 바쁠 때** 검사와
#    알림이 통째로 대기한다.
# 2) 교착: 조사는 재검사 태스크를 큐에 넣고 그 결과를 기다린다. 같은 워커가
#    양쪽을 처리하면 자기가 기다리는 작업을 자기가 실행해야 하는 상태가 되어,
#    동시성이 1이면 영영 풀리지 않는다. 지금까지는 "동시성 2 이상"이라는
#    배포 설정으로 막고 있었는데, 값 하나로 무너지는 방어다. 큐를 나누면
#    재검사는 다른 워커가 처리하므로 그 전제 자체가 필요 없어진다.
#
# 라우팅이 **여기** 있어야 하는 이유: 태스크를 큐에 넣는 쪽은 대부분 API
# 프로세스이고, API는 아래 build_celery_client()로 워커와 별개인 Celery
# 클라이언트를 만든다. 워커 쪽에만 라우팅을 걸면 API가 보낸 태스크는 전부
# 기본 큐로 가서 분리가 무의미해진다.
TASK_ROUTES: dict[str, dict[str, str]] = {
    RUN_CHECK_RUN_TASK_NAME: {"queue": SCANS_QUEUE},
    RUN_SCENARIO_RUN_TASK_NAME: {"queue": SCANS_QUEUE},
    RUN_AGENT_INVESTIGATION_TASK_NAME: {"queue": AGENT_QUEUE},
}


class ScanQueueUnavailableError(Exception):
    """Raised when a check run cannot be submitted to the scan queue."""


def build_celery_client() -> Celery:
    settings = get_settings()
    client = Celery(
        "aim-api",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    client.conf.task_routes = TASK_ROUTES
    return client


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


def enqueue_agent_investigation(
    *,
    check_run_id: UUID,
    incident_id: UUID | None = None,
    trigger: str = "incident",
) -> str:
    # task_id를 검사 단위로 고정해 같은 검사에 대한 중복 조사 큐잉을 막는다.
    task_id = f"agent-investigation:{check_run_id}"
    celery_client = build_celery_client()
    try:
        result = celery_client.send_task(
            RUN_AGENT_INVESTIGATION_TASK_NAME,
            args=[str(check_run_id), str(incident_id) if incident_id else None, trigger],
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
