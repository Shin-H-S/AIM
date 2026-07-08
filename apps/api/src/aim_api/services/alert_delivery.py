import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.config import Settings, get_settings
from aim_api.models.alert import Alert, AlertChannel, AlertStatus
from aim_api.models.project import Project
from aim_api.url_validation import UrlValidationError, validate_service_url

DEFAULT_FROM_EMAIL = "alerts@aim.local"
MAX_DELIVERY_ERROR_LENGTH = 1_000
# Discord rejects content over 2000 characters; keep headroom for safety.
DISCORD_CONTENT_MAX_LENGTH = 1_900


class EmailSender(Protocol):
    def send_message(self, message: EmailMessage) -> None:
        """Send a prepared email message."""


class WebhookSender(Protocol):
    def send(self, *, url: str, payload: dict[str, str]) -> None:
        """Post an alert payload to an incoming webhook URL."""


@dataclass(frozen=True)
class AlertDeliveryResult:
    sent_count: int
    failed_count: int
    skipped_count: int


class AlertNotFoundError(Exception):
    """Raised when an alert does not exist in the requested project."""


class AlertRetryNotAllowedError(Exception):
    """Raised when an alert is not eligible for manual retry."""


class WebhookDeliveryError(Exception):
    """Raised when a webhook endpoint rejects an alert delivery."""


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


@dataclass(frozen=True)
class HttpxWebhookSender:
    timeout_seconds: float

    def send(self, *, url: str, payload: dict[str, str]) -> None:
        response = httpx.post(
            url,
            json=payload,
            timeout=self.timeout_seconds,
            follow_redirects=False,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise WebhookDeliveryError(
                f"Webhook endpoint returned HTTP {response.status_code}."
            )


def deliver_pending_alerts(
    session: Session,
    *,
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
    webhook_sender: WebhookSender | None = None,
    limit: int | None = None,
) -> AlertDeliveryResult:
    runtime_settings = settings or get_settings()
    batch_limit = limit if limit is not None else runtime_settings.alert_delivery_batch_size
    pending_alerts = list_pending_alerts(session, limit=batch_limit)

    sent_count = 0
    failed_count = 0
    skipped_count = 0

    resolved_email_sender = email_sender or build_smtp_email_sender(runtime_settings)
    resolved_webhook_sender = webhook_sender or HttpxWebhookSender(
        timeout_seconds=runtime_settings.alert_webhook_timeout_seconds
    )
    from_email = runtime_settings.smtp_from_email or DEFAULT_FROM_EMAIL

    for alert in pending_alerts:
        if alert.channel == AlertChannel.EMAIL.value:
            if not alert.recipient_email:
                mark_alert_failed(
                    session,
                    alert=alert,
                    error_message="Alert recipient email is missing.",
                )
                failed_count += 1
                continue

            # SMTP가 설정되지 않은 환경에서는 email alert를 PENDING으로 남긴다.
            if resolved_email_sender is None:
                skipped_count += 1
                continue

            try:
                resolved_email_sender.send_message(
                    build_email_message(alert=alert, from_email=from_email)
                )
            except Exception as exc:
                mark_alert_failed(session, alert=alert, error_message=sanitize_delivery_error(exc))
                failed_count += 1
                continue

            mark_alert_sent(session, alert=alert)
            sent_count += 1
            continue

        if alert.channel == AlertChannel.WEBHOOK.value:
            # 발송 시점의 프로젝트 설정을 읽어 URL 수정이 재시도에 바로 반영되게 한다.
            webhook_url = get_project_webhook_url(session, project_id=alert.project_id)
            if not webhook_url:
                mark_alert_failed(
                    session,
                    alert=alert,
                    error_message="Project webhook URL is not configured.",
                )
                failed_count += 1
                continue

            try:
                validate_service_url(webhook_url)
            except UrlValidationError as exc:
                mark_alert_failed(session, alert=alert, error_message=sanitize_delivery_error(exc))
                failed_count += 1
                continue

            payload = build_webhook_payload(
                url=webhook_url,
                subject=alert.subject,
                body=alert.body,
            )
            try:
                resolved_webhook_sender.send(url=webhook_url, payload=payload)
            except Exception as exc:
                mark_alert_failed(session, alert=alert, error_message=sanitize_delivery_error(exc))
                failed_count += 1
                continue

            mark_alert_sent(session, alert=alert)
            sent_count += 1
            continue

        mark_alert_failed(
            session,
            alert=alert,
            error_message=f"Unsupported alert channel: {alert.channel}",
        )
        failed_count += 1

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


def get_project_webhook_url(session: Session, *, project_id: UUID) -> str | None:
    project = session.get(Project, project_id)
    return project.alert_webhook_url if project is not None else None


def build_webhook_payload(*, url: str, subject: str, body: str) -> dict[str, str]:
    text = f"{subject}\n{body}"
    hostname = (urlsplit(url).hostname or "").lower()
    if hostname in {"discord.com", "discordapp.com"} or hostname.endswith(
        (".discord.com", ".discordapp.com")
    ):
        return {"content": text[:DISCORD_CONTENT_MAX_LENGTH]}

    # Slack incoming webhook 형식이며, 그 외 일반 endpoint에도 무난한 기본값.
    return {"text": text}


def list_pending_alerts(session: Session, *, limit: int) -> list[Alert]:
    return list(
        session.scalars(
            select(Alert)
            .where(Alert.status == AlertStatus.PENDING.value)
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


def retry_failed_alert(
    session: Session,
    *,
    project_id: UUID,
    alert_id: UUID,
) -> Alert:
    alert = get_alert_by_id(session, alert_id=alert_id)
    if alert is None or alert.project_id != project_id:
        raise AlertNotFoundError

    if alert.status != AlertStatus.FAILED.value:
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
