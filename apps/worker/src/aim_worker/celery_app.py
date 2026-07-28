import logging
from typing import Any

from aim_api.config import get_settings
from aim_api.observability import configure_logging, new_request_id, request_id_var
from aim_api.services.ops_alerts import notify_ops
from aim_api.services.scan_queue import (
    PURGE_EXPIRED_ARTIFACTS_TASK_NAME,
    SCHEDULE_CHECK_RUNS_TASK_NAME,
)
from celery import Celery
from celery.signals import (
    before_task_publish,
    setup_logging,
    task_failure,
    task_postrun,
    task_prerun,
)

logger = logging.getLogger(__name__)

# 아티팩트 정리 주기. 보존 기간이 일 단위라 자주 돌 이유가 없고, 검사와 슬롯을
# 다투지 않도록 드물게 둔다.
PURGE_EXPIRED_ARTIFACTS_INTERVAL_SECONDS = 60 * 60 * 6

# 태스크 메시지에 실어 보내는 상관관계 헤더 이름.
REQUEST_ID_TASK_HEADER = "aim_request_id"


@setup_logging.connect  # type: ignore[untyped-decorator]
def configure_worker_logging(**_kwargs: Any) -> None:
    """Celery가 자기 로깅 설정을 덮어쓰지 못하게 하고 JSON 출력으로 맞춘다.

    이 시그널에 연결하면 Celery는 로깅에 손을 대지 않는다 — API와 워커의 로그
    형식이 같아야 한 곳에서 request_id로 이어 붙일 수 있다.
    """
    configure_logging(get_settings().app_log_level)


@before_task_publish.connect  # type: ignore[untyped-decorator]
def propagate_request_id(headers: dict[str, Any] | None = None, **_kwargs: Any) -> None:
    """태스크를 큐에 넣을 때 현재 구간의 request_id를 메시지에 싣는다.

    사용자가 검사를 시작한 HTTP 요청과 그 검사를 실제로 수행한 워커 로그가
    같은 키로 묶인다 — 지금까지는 이어 붙일 방법이 아예 없었다.
    """
    if headers is None:
        return

    request_id = request_id_var.get()
    if request_id is not None:
        headers[REQUEST_ID_TASK_HEADER] = request_id


@task_prerun.connect  # type: ignore[untyped-decorator]
def bind_request_id(task: Any = None, **_kwargs: Any) -> None:
    """태스크 실행 구간에 request_id를 건다. 없으면(beat 등) 새로 만든다."""
    inherited_request_id = None
    request = getattr(task, "request", None)
    if request is not None:
        inherited_request_id = getattr(request, REQUEST_ID_TASK_HEADER, None)

    request_id_var.set(inherited_request_id or new_request_id())


@task_postrun.connect  # type: ignore[untyped-decorator]
def clear_request_id(**_kwargs: Any) -> None:
    """워커 프로세스는 재사용되므로 구간이 끝나면 반드시 지운다."""
    request_id_var.set(None)


@task_failure.connect  # type: ignore[untyped-decorator]
def alert_on_task_failure(
    task_id: str | None = None,
    exception: BaseException | None = None,
    sender: Any = None,
    **_kwargs: Any,
) -> None:
    """태스크가 죽으면 운영자에게 알린다.

    워커 태스크 실패는 사용자에게 보이지 않는다 — 검사가 조용히 안 도는 것이
    가장 나쁜 실패 방식이라, 이것만은 반드시 밖으로 나가야 한다.
    """
    task_name = getattr(sender, "name", "unknown")
    logger.error(
        "Celery task failed.",
        extra={"celery_task": task_name, "celery_task_id": task_id},
        exc_info=exception,
    )
    notify_ops(
        title="Worker task failed",
        detail=f"{task_name}\n{type(exception).__name__}: {exception}",
        request_id=request_id_var.get(),
    )


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "aim-worker",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["aim_worker.tasks"],
    )
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_time_limit=300,
        task_soft_time_limit=240,
        worker_prefetch_multiplier=1,
        timezone="UTC",
        beat_schedule={
            "schedule-due-check-runs": {
                "task": SCHEDULE_CHECK_RUNS_TASK_NAME,
                "schedule": float(settings.scan_scheduler_interval_seconds),
            },
            "purge-expired-artifacts": {
                "task": PURGE_EXPIRED_ARTIFACTS_TASK_NAME,
                "schedule": float(PURGE_EXPIRED_ARTIFACTS_INTERVAL_SECONDS),
            },
        },
    )
    return app


celery_app = create_celery_app()
