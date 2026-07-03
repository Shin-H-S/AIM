from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from aim_api.models.scanner_result import AvailabilityResult, LighthouseResult, ScoreResult
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus
from aim_api.models.user import User


@dataclass(frozen=True)
class IncidentTrigger:
    trigger_type: IncidentTriggerType
    severity: IncidentSeverity
    title: str
    summary: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class IncidentSyncResult:
    opened_incidents: list[Incident]
    resolved_incidents: list[Incident]
    alerts: list[Alert]


def sync_incidents_for_check_run(
    session: Session,
    *,
    check_run: CheckRun,
    project: Project,
    availability_result: AvailabilityResult | None,
    lighthouse_result: LighthouseResult | None,
    score_result: ScoreResult,
) -> IncidentSyncResult:
    active_triggers = evaluate_incident_triggers(
        session,
        check_run=check_run,
        project=project,
        availability_result=availability_result,
        lighthouse_result=lighthouse_result,
        score_result=score_result,
    )
    active_triggers_by_type = {trigger.trigger_type.value: trigger for trigger in active_triggers}
    open_incidents = list_open_incidents(session, project_id=project.id)
    open_incidents_by_type = {incident.trigger_type: incident for incident in open_incidents}

    opened_incidents: list[Incident] = []
    resolved_incidents: list[Incident] = []
    alerts: list[Alert] = []
    now = datetime.now(UTC)

    for trigger in active_triggers:
        existing_incident = open_incidents_by_type.get(trigger.trigger_type.value)
        if existing_incident is not None:
            existing_incident.severity = trigger.severity.value
            existing_incident.title = trigger.title
            existing_incident.summary = trigger.summary
            existing_incident.evidence_json = trigger.evidence
            continue

        incident = Incident(
            project_id=project.id,
            opened_check_run_id=check_run.id,
            trigger_type=trigger.trigger_type.value,
            severity=trigger.severity.value,
            status=IncidentStatus.OPEN.value,
            title=trigger.title,
            summary=trigger.summary,
            evidence_json=trigger.evidence,
            started_at=check_run.finished_at or now,
        )
        session.add(incident)
        session.flush()
        opened_incidents.append(incident)
        alert = create_pending_email_alert(
            session,
            project=project,
            incident=incident,
            check_run_id=check_run.id,
            alert_type=AlertType.INCIDENT_OPENED,
        )
        if alert is not None:
            alerts.append(alert)

    for incident in open_incidents:
        if incident.trigger_type in active_triggers_by_type:
            continue

        incident.status = IncidentStatus.RESOLVED.value
        incident.resolved_check_run_id = check_run.id
        incident.resolved_at = check_run.finished_at or now
        resolved_incidents.append(incident)
        alert = create_pending_email_alert(
            session,
            project=project,
            incident=incident,
            check_run_id=check_run.id,
            alert_type=AlertType.INCIDENT_RECOVERED,
        )
        if alert is not None:
            alerts.append(alert)

    session.commit()
    for incident in [*opened_incidents, *resolved_incidents]:
        session.refresh(incident)
    for alert in alerts:
        session.refresh(alert)

    return IncidentSyncResult(
        opened_incidents=opened_incidents,
        resolved_incidents=resolved_incidents,
        alerts=alerts,
    )


def evaluate_incident_triggers(
    session: Session,
    *,
    check_run: CheckRun,
    project: Project,
    availability_result: AvailabilityResult | None,
    lighthouse_result: LighthouseResult | None,
    score_result: ScoreResult,
) -> list[IncidentTrigger]:
    triggers: list[IncidentTrigger] = []

    if availability_result is not None:
        if is_service_connection_failure(availability_result):
            triggers.append(
                IncidentTrigger(
                    trigger_type=IncidentTriggerType.SERVICE_CONNECTION_FAILURE,
                    severity=IncidentSeverity.RISK,
                    title="Service connection failed",
                    summary=availability_result.failure_reason
                    or "The service could not be reached.",
                    evidence={
                        "check_run_id": str(check_run.id),
                        "availability_result_id": str(availability_result.id),
                        "timed_out": availability_result.timed_out,
                        "failure_reason": availability_result.failure_reason,
                    },
                )
            )

        if is_repeated_5xx_response(
            session,
            check_run=check_run,
            availability_result=availability_result,
        ):
            triggers.append(
                IncidentTrigger(
                    trigger_type=IncidentTriggerType.REPEATED_5XX_RESPONSE,
                    severity=IncidentSeverity.RISK,
                    title="Repeated 5xx response detected",
                    summary="The current run and the previous comparable run both returned 5xx.",
                    evidence={
                        "check_run_id": str(check_run.id),
                        "availability_result_id": str(availability_result.id),
                        "status_code": availability_result.status_code,
                    },
                )
            )

        if (
            availability_result.is_available
            and availability_result.response_time_ms is not None
            and availability_result.response_time_ms > project.response_time_threshold_ms
        ):
            triggers.append(
                IncidentTrigger(
                    trigger_type=IncidentTriggerType.RESPONSE_TIME_ABOVE_THRESHOLD,
                    severity=IncidentSeverity.WARNING,
                    title="Response time is above threshold",
                    summary=(
                        f"Response time {availability_result.response_time_ms}ms is above "
                        f"the configured {project.response_time_threshold_ms}ms threshold."
                    ),
                    evidence={
                        "check_run_id": str(check_run.id),
                        "availability_result_id": str(availability_result.id),
                        "response_time_ms": availability_result.response_time_ms,
                        "threshold_ms": project.response_time_threshold_ms,
                    },
                )
            )

    if (
        lighthouse_result is not None
        and lighthouse_result.is_successful
        and lighthouse_result.performance_score is not None
        and lighthouse_result.performance_score < project.quality_score_threshold
    ):
        triggers.append(
            IncidentTrigger(
                trigger_type=IncidentTriggerType.PERFORMANCE_SCORE_BELOW_THRESHOLD,
                severity=IncidentSeverity.WARNING,
                title="Performance score is below threshold",
                summary=(
                    f"Performance score {lighthouse_result.performance_score} is below "
                    f"the configured {project.quality_score_threshold} threshold."
                ),
                evidence={
                    "check_run_id": str(check_run.id),
                    "lighthouse_result_id": str(lighthouse_result.id),
                    "performance_score": lighthouse_result.performance_score,
                    "threshold": project.quality_score_threshold,
                },
            )
        )

    failed_scenario_run = get_failed_linked_scenario_run(
        session,
        check_run_id=check_run.id,
    )
    if failed_scenario_run is not None:
        triggers.append(
            IncidentTrigger(
                trigger_type=IncidentTriggerType.CRITICAL_SCENARIO_FAILURE,
                severity=IncidentSeverity.RISK,
                title="Critical scenario failed",
                summary=failed_scenario_run.failure_reason or "A linked critical scenario failed.",
                evidence={
                    "check_run_id": str(check_run.id),
                    "scenario_run_id": str(failed_scenario_run.id),
                    "failure_reason": failed_scenario_run.failure_reason,
                    "deployment_risk": score_result.deployment_risk,
                },
            )
        )

    return triggers


def is_service_connection_failure(availability_result: AvailabilityResult) -> bool:
    return not availability_result.is_available and availability_result.status_code is None


def is_5xx_status(status_code: int | None) -> bool:
    return status_code is not None and 500 <= status_code <= 599


def is_repeated_5xx_response(
    session: Session,
    *,
    check_run: CheckRun,
    availability_result: AvailabilityResult,
) -> bool:
    if not is_5xx_status(availability_result.status_code):
        return False

    previous_availability_result = get_previous_availability_result(
        session,
        project_id=check_run.project_id,
        check_run_id=check_run.id,
    )
    return previous_availability_result is not None and is_5xx_status(
        previous_availability_result.status_code
    )


def get_previous_availability_result(
    session: Session,
    *,
    project_id: UUID,
    check_run_id: UUID,
) -> AvailabilityResult | None:
    current_check_run = session.get(CheckRun, check_run_id)
    if current_check_run is None:
        return None

    terminal_statuses = [
        CheckRunStatus.COMPLETED.value,
        CheckRunStatus.FAILED.value,
        CheckRunStatus.CANCELLED.value,
    ]
    return session.scalar(
        select(AvailabilityResult)
        .join(CheckRun, CheckRun.id == AvailabilityResult.check_run_id)
        .where(
            CheckRun.project_id == project_id,
            CheckRun.id != check_run_id,
            CheckRun.status.in_(terminal_statuses),
            CheckRun.created_at < current_check_run.created_at,
        )
        .order_by(CheckRun.created_at.desc(), CheckRun.id.desc())
        .limit(1)
    )


def get_failed_linked_scenario_run(
    session: Session,
    *,
    check_run_id: UUID,
) -> ScenarioRun | None:
    return session.scalar(
        select(ScenarioRun)
        .where(
            ScenarioRun.check_run_id == check_run_id,
            ScenarioRun.status == ScenarioRunStatus.FAILED.value,
        )
        .order_by(ScenarioRun.finished_at.desc(), ScenarioRun.id.desc())
        .limit(1)
    )


def list_open_incidents(session: Session, *, project_id: UUID) -> list[Incident]:
    return list(
        session.scalars(
            select(Incident)
            .where(
                Incident.project_id == project_id,
                Incident.status == IncidentStatus.OPEN.value,
            )
            .order_by(Incident.started_at.asc(), Incident.id.asc())
        )
    )


def list_incidents(
    session: Session,
    *,
    project_id: UUID,
    limit: int,
    offset: int,
) -> list[Incident]:
    return list(
        session.scalars(
            select(Incident)
            .where(Incident.project_id == project_id)
            .order_by(Incident.started_at.desc(), Incident.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def list_alerts(
    session: Session,
    *,
    project_id: UUID,
    limit: int,
    offset: int,
) -> list[Alert]:
    return list(
        session.scalars(
            select(Alert)
            .where(Alert.project_id == project_id)
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def create_pending_email_alert(
    session: Session,
    *,
    project: Project,
    incident: Incident,
    check_run_id: UUID,
    alert_type: AlertType,
) -> Alert | None:
    if not project.alert_email_enabled:
        return None

    owner_email = get_project_owner_email(session, project=project)
    alert = Alert(
        project_id=project.id,
        incident_id=incident.id,
        check_run_id=check_run_id,
        alert_type=alert_type.value,
        trigger_type=incident.trigger_type,
        channel=AlertChannel.EMAIL.value,
        status=AlertStatus.PENDING.value,
        recipient_email=project.alert_recipient_email or owner_email,
        subject=build_alert_subject(project=project, incident=incident, alert_type=alert_type),
        body=build_alert_body(project=project, incident=incident, alert_type=alert_type),
        delivery_attempts=0,
    )
    session.add(alert)
    return alert


def get_project_owner_email(session: Session, *, project: Project) -> str | None:
    if project.owner_id is None:
        return None

    owner = session.get(User, project.owner_id)
    return owner.email if owner is not None else None


def build_alert_subject(
    *,
    project: Project,
    incident: Incident,
    alert_type: AlertType,
) -> str:
    if alert_type == AlertType.INCIDENT_RECOVERED:
        return f"[AIM] {project.name}: recovered from {incident.title}"

    return f"[AIM] {project.name}: {incident.title}"


def build_alert_body(
    *,
    project: Project,
    incident: Incident,
    alert_type: AlertType,
) -> str:
    if alert_type == AlertType.INCIDENT_RECOVERED:
        resolved_at = incident.resolved_at.isoformat() if incident.resolved_at else "unknown"
        return (
            f"Project: {project.name}\n"
            f"Incident: {incident.title}\n"
            f"Status: {IncidentStatus.RESOLVED.value}\n"
            f"Resolved at: {resolved_at}\n"
            f"Summary: The incident trigger is no longer active."
        )

    return (
        f"Project: {project.name}\n"
        f"Incident: {incident.title}\n"
        f"Severity: {incident.severity}\n"
        f"Status: {incident.status}\n"
        f"Started at: {incident.started_at.isoformat()}\n"
        f"Summary: {incident.summary}"
    )
