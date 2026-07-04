from aim_api.config import get_settings
from aim_api.services.scan_queue import SCHEDULE_CHECK_RUNS_TASK_NAME
from celery import Celery


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
        },
    )
    return app


celery_app = create_celery_app()
