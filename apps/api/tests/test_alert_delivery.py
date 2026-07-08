from collections.abc import Iterator
from datetime import UTC, datetime
from email.message import EmailMessage
from uuid import uuid4

import pytest
from aim_api.config import Settings
from aim_api.database import Base
from aim_api.models.alert import (
    Alert,
    AlertChannel,
    AlertStatus,
    AlertType,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentTriggerType,
)
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import alert_delivery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T000/B000/XXXX"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1234567890/abcdefg"


class FakeEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)


class FailingEmailSender:
    def send_message(self, message: EmailMessage) -> None:
        _ = message
        raise RuntimeError("SMTP server unavailable")


class FakeWebhookSender:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, dict[str, str]]] = []

    def send(self, *, url: str, payload: dict[str, str]) -> None:
        self.deliveries.append((url, payload))


class FailingWebhookSender:
    def send(self, *, url: str, payload: dict[str, str]) -> None:
        _ = (url, payload)
        raise alert_delivery.WebhookDeliveryError("Webhook endpoint returned HTTP 404.")


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_pending_alert(
    session: Session,
    *,
    recipient_email: str | None = "owner@example.com",
    status: AlertStatus = AlertStatus.PENDING,
    channel: AlertChannel = AlertChannel.EMAIL,
    project_webhook_url: str | None = None,
) -> Alert:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC),
        environment="production",
        alert_webhook_url=project_webhook_url,
    )
    session.add(project)
    session.flush()
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED.value,
        trigger_source="manual",
        queued_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    session.add(check_run)
    session.flush()
    incident = Incident(
        project_id=project.id,
        opened_check_run_id=check_run.id,
        trigger_type=IncidentTriggerType.SERVICE_CONNECTION_FAILURE.value,
        severity=IncidentSeverity.RISK.value,
        status=IncidentStatus.OPEN.value,
        title="Service connection failed",
        summary="Connection timed out.",
        evidence_json={"check_run_id": str(check_run.id)},
        started_at=datetime.now(UTC),
    )
    session.add(incident)
    session.flush()
    alert = Alert(
        project_id=project.id,
        incident_id=incident.id,
        check_run_id=check_run.id,
        alert_type=AlertType.INCIDENT_OPENED.value,
        trigger_type=IncidentTriggerType.SERVICE_CONNECTION_FAILURE.value,
        channel=channel.value,
        status=status.value,
        recipient_email=recipient_email if channel == AlertChannel.EMAIL else None,
        subject="[AIM] AIM Website: Service connection failed",
        body="Project: AIM Website\nSummary: Connection timed out.",
        delivery_attempts=0,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def smtp_settings() -> Settings:
    return Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_from_email="alerts@example.com",
        smtp_use_tls=True,
        alert_delivery_batch_size=25,
    )


def test_deliver_pending_alerts_sends_email_and_marks_sent(session: Session) -> None:
    alert = create_pending_alert(session)
    sender = FakeEmailSender()

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=smtp_settings(),
        email_sender=sender,
    )

    session.refresh(alert)
    assert result.sent_count == 1
    assert result.failed_count == 0
    assert result.skipped_count == 0
    assert alert.status == AlertStatus.SENT.value
    assert alert.delivery_attempts == 1
    assert alert.sent_at is not None
    assert alert.last_error is None
    assert len(sender.messages) == 1
    assert sender.messages[0]["From"] == "alerts@example.com"
    assert sender.messages[0]["To"] == "owner@example.com"
    assert sender.messages[0]["Subject"] == "[AIM] AIM Website: Service connection failed"


def test_deliver_pending_alerts_keeps_email_pending_when_smtp_is_not_configured(
    session: Session,
) -> None:
    alert = create_pending_alert(session)

    result = alert_delivery.deliver_pending_alerts(session, settings=Settings())

    session.refresh(alert)
    assert result.sent_count == 0
    assert result.failed_count == 0
    assert result.skipped_count == 1
    assert alert.status == AlertStatus.PENDING.value
    assert alert.delivery_attempts == 0
    assert alert.sent_at is None
    assert alert.last_error is None


def test_deliver_pending_alerts_marks_missing_recipient_failed(
    session: Session,
) -> None:
    alert = create_pending_alert(session, recipient_email=None)
    sender = FakeEmailSender()

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=smtp_settings(),
        email_sender=sender,
    )

    session.refresh(alert)
    assert result.sent_count == 0
    assert result.failed_count == 1
    assert result.skipped_count == 0
    assert alert.status == AlertStatus.FAILED.value
    assert alert.delivery_attempts == 1
    assert alert.last_error == "Alert recipient email is missing."
    assert sender.messages == []


def test_deliver_pending_alerts_marks_email_sender_failure_failed(
    session: Session,
) -> None:
    alert = create_pending_alert(session)

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=smtp_settings(),
        email_sender=FailingEmailSender(),
    )

    session.refresh(alert)
    assert result.sent_count == 0
    assert result.failed_count == 1
    assert result.skipped_count == 0
    assert alert.status == AlertStatus.FAILED.value
    assert alert.delivery_attempts == 1
    assert alert.sent_at is None
    assert alert.last_error == "SMTP server unavailable"


def test_deliver_pending_alerts_sends_webhook_and_marks_sent(session: Session) -> None:
    alert = create_pending_alert(
        session,
        channel=AlertChannel.WEBHOOK,
        project_webhook_url=SLACK_WEBHOOK_URL,
    )
    sender = FakeWebhookSender()

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=Settings(),
        webhook_sender=sender,
    )

    session.refresh(alert)
    assert result.sent_count == 1
    assert result.failed_count == 0
    assert alert.status == AlertStatus.SENT.value
    assert alert.delivery_attempts == 1
    assert alert.sent_at is not None
    assert len(sender.deliveries) == 1
    url, payload = sender.deliveries[0]
    assert url == SLACK_WEBHOOK_URL
    assert payload == {
        "text": (
            "[AIM] AIM Website: Service connection failed\n"
            "Project: AIM Website\nSummary: Connection timed out."
        )
    }


def test_deliver_pending_alerts_marks_missing_webhook_url_failed(session: Session) -> None:
    alert = create_pending_alert(
        session,
        channel=AlertChannel.WEBHOOK,
        project_webhook_url=None,
    )
    sender = FakeWebhookSender()

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=Settings(),
        webhook_sender=sender,
    )

    session.refresh(alert)
    assert result.failed_count == 1
    assert alert.status == AlertStatus.FAILED.value
    assert alert.last_error == "Project webhook URL is not configured."
    assert sender.deliveries == []


def test_deliver_pending_alerts_rejects_unsafe_webhook_url(session: Session) -> None:
    alert = create_pending_alert(
        session,
        channel=AlertChannel.WEBHOOK,
        project_webhook_url="https://127.0.0.1/hook",
    )
    sender = FakeWebhookSender()

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=Settings(),
        webhook_sender=sender,
    )

    session.refresh(alert)
    assert result.failed_count == 1
    assert alert.status == AlertStatus.FAILED.value
    assert alert.last_error is not None
    assert sender.deliveries == []


def test_deliver_pending_alerts_marks_webhook_sender_failure_failed(session: Session) -> None:
    alert = create_pending_alert(
        session,
        channel=AlertChannel.WEBHOOK,
        project_webhook_url=SLACK_WEBHOOK_URL,
    )

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=Settings(),
        webhook_sender=FailingWebhookSender(),
    )

    session.refresh(alert)
    assert result.failed_count == 1
    assert alert.status == AlertStatus.FAILED.value
    assert alert.last_error == "Webhook endpoint returned HTTP 404."


def test_deliver_pending_alerts_handles_mixed_channels(session: Session) -> None:
    email_alert = create_pending_alert(session)
    webhook_alert = create_pending_alert(
        session,
        channel=AlertChannel.WEBHOOK,
        project_webhook_url=SLACK_WEBHOOK_URL,
    )
    webhook_sender = FakeWebhookSender()

    # SMTP 미설정: email은 PENDING 유지, webhook은 발송된다.
    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=Settings(),
        webhook_sender=webhook_sender,
    )

    session.refresh(email_alert)
    session.refresh(webhook_alert)
    assert result.sent_count == 1
    assert result.skipped_count == 1
    assert email_alert.status == AlertStatus.PENDING.value
    assert webhook_alert.status == AlertStatus.SENT.value


def test_build_webhook_payload_targets_discord_content() -> None:
    payload = alert_delivery.build_webhook_payload(
        url=DISCORD_WEBHOOK_URL,
        subject="subject",
        body="body",
    )

    assert payload == {"content": "subject\nbody"}


def test_build_webhook_payload_truncates_discord_content() -> None:
    payload = alert_delivery.build_webhook_payload(
        url=DISCORD_WEBHOOK_URL,
        subject="s",
        body="b" * 3000,
    )

    assert len(payload["content"]) == alert_delivery.DISCORD_CONTENT_MAX_LENGTH


def test_build_webhook_payload_defaults_to_slack_text() -> None:
    for url in (SLACK_WEBHOOK_URL, "https://example.com/custom-hook"):
        payload = alert_delivery.build_webhook_payload(url=url, subject="s", body="b")
        assert payload == {"text": "s\nb"}


def test_list_pending_alerts_ignores_non_pending_alerts(session: Session) -> None:
    pending_alert = create_pending_alert(session)
    _ = create_pending_alert(session, status=AlertStatus.SENT)

    alerts = alert_delivery.list_pending_alerts(session, limit=10)

    assert [alert.id for alert in alerts] == [pending_alert.id]


def test_deliver_pending_alerts_respects_batch_limit(session: Session) -> None:
    first_alert = create_pending_alert(session, recipient_email="first@example.com")
    second_alert = create_pending_alert(session, recipient_email="second@example.com")
    sender = FakeEmailSender()

    result = alert_delivery.deliver_pending_alerts(
        session,
        settings=smtp_settings(),
        email_sender=sender,
        limit=1,
    )

    session.refresh(first_alert)
    session.refresh(second_alert)
    assert result.sent_count == 1
    assert first_alert.status == AlertStatus.SENT.value
    assert second_alert.status == AlertStatus.PENDING.value
    assert sender.messages[0]["To"] == "first@example.com"


def test_retry_failed_alert_resets_delivery_error(session: Session) -> None:
    alert = create_pending_alert(session, status=AlertStatus.FAILED)
    alert.delivery_attempts = 2
    alert.last_error = "SMTP server unavailable"
    session.commit()

    retried_alert = alert_delivery.retry_failed_alert(
        session,
        project_id=alert.project_id,
        alert_id=alert.id,
    )

    assert retried_alert.status == AlertStatus.PENDING.value
    assert retried_alert.delivery_attempts == 2
    assert retried_alert.last_error is None
    assert retried_alert.sent_at is None


def test_retry_failed_alert_allows_webhook_channel(session: Session) -> None:
    alert = create_pending_alert(
        session,
        status=AlertStatus.FAILED,
        channel=AlertChannel.WEBHOOK,
        project_webhook_url=SLACK_WEBHOOK_URL,
    )

    retried_alert = alert_delivery.retry_failed_alert(
        session,
        project_id=alert.project_id,
        alert_id=alert.id,
    )

    assert retried_alert.status == AlertStatus.PENDING.value


def test_retry_failed_alert_rejects_non_failed_alert(session: Session) -> None:
    alert = create_pending_alert(session)

    with pytest.raises(alert_delivery.AlertRetryNotAllowedError):
        alert_delivery.retry_failed_alert(
            session,
            project_id=alert.project_id,
            alert_id=alert.id,
        )


def test_retry_failed_alert_requires_matching_project(session: Session) -> None:
    alert = create_pending_alert(session, status=AlertStatus.FAILED)

    with pytest.raises(alert_delivery.AlertNotFoundError):
        alert_delivery.retry_failed_alert(
            session,
            project_id=uuid4(),
            alert_id=alert.id,
        )


def test_build_smtp_email_sender_requires_host_and_from_email() -> None:
    assert alert_delivery.build_smtp_email_sender(Settings()) is None

    sender = alert_delivery.build_smtp_email_sender(smtp_settings())

    assert sender is not None
    assert sender.host == "smtp.example.com"
