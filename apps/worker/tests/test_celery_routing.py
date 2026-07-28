"""큐 라우팅 검증.

조사 태스크가 검사와 같은 큐로 돌아가면 두 가지가 되살아난다: 조사가 검사를
굶기는 문제와, 조사가 자기 재검사를 기다리는 교착. 그래서 라우팅은 설정이
아니라 계약으로 지킨다.
"""

from aim_api.services import scan_queue
from aim_api.services.scan_queue import (
    AGENT_QUEUE,
    DELIVER_EMAIL_ALERTS_TASK_NAME,
    PURGE_EXPIRED_ARTIFACTS_TASK_NAME,
    RUN_AGENT_INVESTIGATION_TASK_NAME,
    RUN_AI_REPORT_TASK_NAME,
    RUN_CHECK_RUN_TASK_NAME,
    RUN_SCENARIO_RUN_TASK_NAME,
    SCANS_QUEUE,
    SCHEDULE_CHECK_RUNS_TASK_NAME,
)
from aim_worker.celery_app import celery_app


def routed_queue(task_name: str) -> str | None:
    route = celery_app.conf.task_routes.get(task_name)
    return route["queue"] if route else None


def test_agent_investigation_is_isolated_from_scans() -> None:
    """이 둘이 같아지면 교착과 굶주림이 함께 돌아온다."""
    assert routed_queue(RUN_AGENT_INVESTIGATION_TASK_NAME) == AGENT_QUEUE
    assert routed_queue(RUN_CHECK_RUN_TASK_NAME) == SCANS_QUEUE
    assert routed_queue(RUN_AGENT_INVESTIGATION_TASK_NAME) != routed_queue(RUN_CHECK_RUN_TASK_NAME)


def test_scenario_runs_share_the_scan_queue() -> None:
    """재검사는 검사와 시나리오를 함께 돌린다 — 같은 큐여야 한다."""
    assert routed_queue(RUN_SCENARIO_RUN_TASK_NAME) == SCANS_QUEUE


def test_short_tasks_stay_on_the_default_queue() -> None:
    """기본 큐 이름을 바꾸면 배포 시점에 남아 있던 메시지가 미아가 된다."""
    for task_name in (
        RUN_AI_REPORT_TASK_NAME,
        DELIVER_EMAIL_ALERTS_TASK_NAME,
        SCHEDULE_CHECK_RUNS_TASK_NAME,
        PURGE_EXPIRED_ARTIFACTS_TASK_NAME,
    ):
        assert routed_queue(task_name) is None

    assert celery_app.conf.task_default_queue == "celery"


def test_the_api_client_routes_too() -> None:
    """태스크를 큐에 넣는 쪽은 대부분 API다.

    API는 워커와 별개인 Celery 클라이언트를 만든다. 여기에 라우팅이 빠지면
    API가 보낸 태스크가 전부 기본 큐로 가고, 전용 워커는 빈 큐만 바라보며
    분리가 통째로 무의미해진다 — 설정만 보면 멀쩡해 보이기 때문에 특히 위험하다.
    """
    client = scan_queue.build_celery_client()

    assert client.conf.task_routes[RUN_AGENT_INVESTIGATION_TASK_NAME] == {"queue": AGENT_QUEUE}
    assert client.conf.task_routes[RUN_CHECK_RUN_TASK_NAME] == {"queue": SCANS_QUEUE}


def test_every_routed_queue_has_a_worker_consuming_it() -> None:
    """compose의 --queues 목록과 라우팅이 어긋나면 태스크가 조용히 멈춘다."""
    compose = __import__("pathlib").Path("infra/compose.yaml").read_text(encoding="utf-8")

    assert "--queues=scans,celery" in compose
    assert "--queues=agent" in compose
