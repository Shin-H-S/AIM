import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.config import Settings, get_settings
from aim_api.models.alert import Alert, AlertChannel, AlertStatus

DEFAULT_FROM_EMAIL = "alerts@aim.local"
MAX_DELIVERY_ERROR_LENGTH = 1_000


class EmailSender(Protocol):
    def send_message(self, message: EmailMessage) -> None:
        """Send a prepared email message."""


@dataclass(frozen=True)
class AlertDeliveryResult:
    sent_count: int
    failed_count: int
    skipped_count: int


class AlertNotFoundError(Exception):
    """Raised when an alert does not exist in the requested project."""


class AlertRetryNotAllowedError(Exception):
    """Raised when an alert is not eligible for manual retry."""


@dataclass(frozen=True)
class SmtpEmailSender:
    host: str
    port: int
    username: str | None
    password: str | None
    use_tls: bool
    timeout_seconds: float

    def send_message(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as smtp:
            if self.use_tls:
                smtp.starttls()

            if self.username is not None:
                smtp.login(self.username, self.password or "")

            smtp.send_message(message)


def deliver_pending_email_alerts(
    session: Session,
    *,
    settings: Settings | None = None,
    sender: EmailSender | None = None,
    limit: int | None = None,
) -> AlertDeliveryResult:
    runtime_settings = settings or get_settings()
    batch_limit = limit if limit is not None else runtime_settings.alert_delivery_batch_size
    pending_alerts = list_pending_email_alerts(session, limit=batch_limit)

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    deliverable_alerts: list[Alert] = []

    for alert in pending_alerts:
        if not alert.recipient_email:
            mark_alert_failed(
                session,
                alert=alert,
                error_message="Alert recipient email is missing.",
            )
            failed_count += 1
            continue

        deliverable_alerts.append(alert)

    if not deliverable_alerts:
        return AlertDeliveryResult(
            sent_count=sent_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
        )

    email_sender = sender or build_smtp_email_sender(runtime_settings)
    if email_sender is None:
        return AlertDeliveryResult(
            sent_count=sent_count,
            failed_count=failed_count,
            skipped_count=len(deliverable_alerts),
        )

    from_email = runtime_settings.smtp_from_email or DEFAULT_FROM_EMAIL
    for alert in deliverable_alerts:
        try:
            email_sender.send_message(build_email_message(alert=alert, from_email=from_email))
        except Exception as exc:
            mark_alert_failed(
                session,
                alert=alert,
                error_message=sanitize_delivery_error(exc),
            )
            failed_count += 1
            continue

        mark_alert_sent(session, alert=alert)
        sent_count += 1

    return AlertDeliveryResult(
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )


def build_smtp_email_sender(settings: Settings) -> SmtpEmailSender | None:
    if not settings.smtp_host or not settings.smtp_from_email:
        return None

    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        timeout_seconds=settings.smtp_timeout_seconds,
    )


def list_pending_email_alerts(session: Session, *, limit: int) -> list[Alert]:
    return list(
        session.scalars(
            select(Alert)
            .where(
                Alert.channel == AlertChannel.EMAIL.value,
                Alert.status == AlertStatus.PENDING.value,
            )
            .order_by(Alert.created_at.asc(), Alert.id.asc())
            .limit(limit)
        )
    )


def build_email_message(*, alert: Alert, from_email: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = from_email
    message["To"] = alert.recipient_email or ""
    message["Subject"] = alert.subject
    message.set_content(alert.body)
    return message


def mark_alert_sent(session: Session, *, alert: Alert) -> Alert:
    alert.status = AlertStatus.SENT.value
    alert.delivery_attempts += 1
    alert.last_error = None
    alert.sent_at = datetime.now(UTC)
    session.commit()
    session.refresh(alert)
    return alert


def mark_alert_failed(
    session: Session,
    *,
    alert: Alert,
    error_message: str,
) -> Alert:
    alert.status = AlertStatus.FAILED.value
    alert.delivery_attempts += 1
    alert.last_error = error_message[:MAX_DELIVERY_ERROR_LENGTH]
    alert.sent_at = None
    session.commit()
    session.refresh(alert)
    return alert


def retry_failed_email_alert(
    session: Session,
    *,
    project_id: UUID,
    alert_id: UUID,
) -> Alert:
    alert = get_alert_by_id(session, alert_id=alert_id)
    if alert is None or alert.project_id != project_id:
        raise AlertNotFoundError

    if alert.channel != AlertChannel.EMAIL.value or alert.status != AlertStatus.FAILED.value:
        raise AlertRetryNotAllowedError

    alert.status = AlertStatus.PENDING.value
    alert.last_error = None
    alert.sent_at = None
    session.commit()
    session.refresh(alert)
    return alert


def mark_alert_retry_enqueue_failed(
    session: Session,
    *,
    alert: Alert,
    error_message: str,
) -> Alert:
    alert.status = AlertStatus.FAILED.value
    alert.last_error = error_message[:MAX_DELIVERY_ERROR_LENGTH]
    alert.sent_at = None
    session.commit()
    session.refresh(alert)
    return alert


def get_alert_by_id(session: Session, *, alert_id: UUID) -> Alert | None:
    return session.get(Alert, alert_id)


def sanitize_delivery_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__
