from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from aim_api.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class IncidentTriggerType(StrEnum):
    SERVICE_CONNECTION_FAILURE = "SERVICE_CONNECTION_FAILURE"
    REPEATED_5XX_RESPONSE = "REPEATED_5XX_RESPONSE"
    CRITICAL_SCENARIO_FAILURE = "CRITICAL_SCENARIO_FAILURE"
    PERFORMANCE_SCORE_BELOW_THRESHOLD = "PERFORMANCE_SCORE_BELOW_THRESHOLD"
    RESPONSE_TIME_ABOVE_THRESHOLD = "RESPONSE_TIME_ABOVE_THRESHOLD"


class IncidentSeverity(StrEnum):
    WARNING = "WARNING"
    RISK = "RISK"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class AlertType(StrEnum):
    INCIDENT_OPENED = "INCIDENT_OPENED"
    INCIDENT_RECOVERED = "INCIDENT_RECOVERED"
    DEPLOY_SUMMARY = "DEPLOY_SUMMARY"


# incident와 무관한 배포 요약 알림이 alerts.trigger_type에 기록하는 값.
DEPLOY_SUMMARY_TRIGGER_TYPE = "DEPLOY_CHECK_COMPLETED"


class AlertChannel(StrEnum):
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"


class AlertStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            (
                "trigger_type IN ("
                "'SERVICE_CONNECTION_FAILURE', "
                "'REPEATED_5XX_RESPONSE', "
                "'CRITICAL_SCENARIO_FAILURE', "
                "'PERFORMANCE_SCORE_BELOW_THRESHOLD', "
                "'RESPONSE_TIME_ABOVE_THRESHOLD')"
            ),
            name="ck_incidents_trigger_type",
        ),
        CheckConstraint("severity IN ('WARNING', 'RISK')", name="ck_incidents_severity"),
        CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_incidents_status"),
        CheckConstraint(
            "(status = 'OPEN' AND resolved_at IS NULL) OR "
            "(status = 'RESOLVED' AND resolved_at IS NOT NULL)",
            name="ck_incidents_resolved_at_matches_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opened_check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resolved_check_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="SET NULL"),
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=IncidentStatus.OPEN.value,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('INCIDENT_OPENED', 'INCIDENT_RECOVERED', 'DEPLOY_SUMMARY')",
            name="ck_alerts_alert_type",
        ),
        CheckConstraint(
            (
                "trigger_type IN ("
                "'SERVICE_CONNECTION_FAILURE', "
                "'REPEATED_5XX_RESPONSE', "
                "'CRITICAL_SCENARIO_FAILURE', "
                "'PERFORMANCE_SCORE_BELOW_THRESHOLD', "
                "'RESPONSE_TIME_ABOVE_THRESHOLD', "
                "'DEPLOY_CHECK_COMPLETED')"
            ),
            name="ck_alerts_trigger_type",
        ),
        CheckConstraint("channel IN ('EMAIL', 'WEBHOOK')", name="ck_alerts_channel"),
        CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_alerts_status"),
        CheckConstraint(
            "delivery_attempts >= 0",
            name="ck_alerts_delivery_attempts_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    check_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="SET NULL"),
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AlertChannel.EMAIL.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AlertStatus.PENDING.value,
        index=True,
    )
    recipient_email: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
