from aim_api.config import get_settings
from aim_api.services.scan_queue import (
    PURGE_EXPIRED_ARTIFACTS_TASK_NAME,
    SCHEDULE_CHECK_RUNS_TASK_NAME,
)
from celery import Celery

# 아티팩트 정리 주기. 보존 기간이 일 단위라 자주 돌 이유가 없고, 검사와 슬롯을
# 다투지 않도록 드물게 둔다.
PURGE_EXPIRED_ARTIFACTS_INTERVAL_SECONDS = 60 * 60 * 6


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
