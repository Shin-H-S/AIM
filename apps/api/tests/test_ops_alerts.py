import pytest
from aim_api.config import Settings
from aim_api.services import ops_alerts


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, str]]] = []

    def send(self, *, url: str, payload: dict[str, str]) -> None:
        self.sent.append((url, payload))


class FailingSender:
    def send(self, *, url: str, payload: dict[str, str]) -> None:
        raise RuntimeError("webhook is down")


def settings_with_webhook(url: str | None) -> Settings:
    return Settings(_env_file=None, ops_webhook_url=url)


def test_ops_alert_is_delivered_to_the_configured_webhook() -> None:
    sender = RecordingSender()

    delivered = ops_alerts.notify_ops(
        title="API unhandled exception",
        detail="ValueError: boom",
        request_id="correlation-1",
        settings=settings_with_webhook("https://discord.example/webhook"),
        sender=sender,
    )

    assert delivered is True
    url, payload = sender.sent[0]
    assert url == "https://discord.example/webhook"
    assert "API unhandled exception" in payload["content"]
    assert "correlation-1" in payload["content"]
    assert "ValueError: boom" in payload["content"]


def test_no_webhook_configured_is_not_an_error() -> None:
    """운영 webhook은 선택 사항이다 — 미설정이 장애 처리를 막으면 안 된다."""
    sender = RecordingSender()

    delivered = ops_alerts.notify_ops(
        title="API unhandled exception",
        detail="ValueError: boom",
        settings=settings_with_webhook(None),
        sender=sender,
    )

    assert delivered is False
    assert sender.sent == []


def test_a_failing_webhook_never_raises() -> None:
    """알림 실패가 원래 장애 처리 흐름까지 깨면 상황이 더 나빠진다."""
    delivered = ops_alerts.notify_ops(
        title="Worker task failed",
        detail="boom",
        settings=settings_with_webhook("https://discord.example/webhook"),
        sender=FailingSender(),
    )

    assert delivered is False


def test_long_details_are_truncated_for_the_webhook() -> None:
    sender = RecordingSender()

    ops_alerts.notify_ops(
        title="API unhandled exception",
        detail="x" * 5_000,
        settings=settings_with_webhook("https://discord.example/webhook"),
        sender=sender,
    )

    _, payload = sender.sent[0]
    assert len(payload["content"]) <= ops_alerts.MAX_OPS_ALERT_LENGTH
    assert payload["content"].endswith("```")


def test_a_missing_request_id_is_omitted_from_the_body() -> None:
    sender = RecordingSender()

    ops_alerts.notify_ops(
        title="Worker task failed",
        detail="boom",
        request_id=None,
        settings=settings_with_webhook("https://discord.example/webhook"),
        sender=sender,
    )

    _, payload = sender.sent[0]
    assert "request_id" not in payload["content"]


@pytest.mark.parametrize("title", ["API unhandled exception", "Worker task failed"])
def test_the_title_is_always_present(title: str) -> None:
    sender = RecordingSender()

    ops_alerts.notify_ops(
        title=title,
        detail="boom",
        settings=settings_with_webhook("https://discord.example/webhook"),
        sender=sender,
    )

    _, payload = sender.sent[0]
    assert title in payload["content"]


def test_background_notify_delivers_off_the_calling_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """요청 경로에서 webhook timeout만큼 붙잡히면 fail-open의 목적이 무너진다."""
    import threading

    delivered: list[tuple[str, str]] = []

    def recording_notify(
        *, title: str, detail: str, request_id: str | None = None, **_: object
    ) -> bool:
        delivered.append((title, threading.current_thread().name))
        return True

    monkeypatch.setattr(ops_alerts, "notify_ops", recording_notify)

    thread = ops_alerts.notify_ops_in_background(title="outage", detail="d")
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(delivered) == 1
    title, thread_name = delivered[0]
    assert title == "outage"
    assert thread_name != threading.main_thread().name


def test_background_notify_swallows_delivery_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """알림 실패가 어디로도 전파되면 안 된다 — 스레드는 조용히 끝나야 한다."""

    def failing_notify(**_: object) -> bool:
        raise RuntimeError("must never escape")

    monkeypatch.setattr(ops_alerts, "notify_ops", failing_notify)

    thread = ops_alerts.notify_ops_in_background(title="outage", detail="d")
    thread.join(timeout=5)

    assert not thread.is_alive()
