from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.config import Settings, get_settings
from aim_api.models.alert import (
    DEPLOY_SUMMARY_TRIGGER_TYPE,
    Alert,
    AlertChannel,
    AlertStatus,
    AlertType,
)
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import RunComparison, ScoreResult
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus
from aim_api.services import run_comparisons as run_comparison_service

DEPLOY_TRIGGER_SOURCE = "deploy"
SUMMARY_SUBJECT_MAX_LENGTH = 255

RISK_KO = {
    "STABLE": "안정",
    "WARNING": "주의",
    "RISK": "위험",
}

TERMINAL_SUMMARY_STATUSES = {
    CheckRunStatus.COMPLETED.value,
    CheckRunStatus.FAILED.value,
}

PENDING_SCENARIO_RUN_STATUSES = (
    ScenarioRunStatus.QUEUED.value,
    ScenarioRunStatus.RUNNING.value,
)


def has_unfinished_scenario_runs(session: Session, *, check_run_id: UUID) -> bool:
    statement = select(ScenarioRun.id).where(
        ScenarioRun.check_run_id == check_run_id,
        ScenarioRun.status.in_(PENDING_SCENARIO_RUN_STATUSES),
    )
    return session.scalar(statement) is not None


def deploy_summary_exists(session: Session, *, check_run_id: UUID) -> bool:
    statement = select(Alert.id).where(
        Alert.check_run_id == check_run_id,
        Alert.alert_type == AlertType.DEPLOY_SUMMARY.value,
    )
    return session.scalar(statement) is not None


def create_deploy_summary_alerts(
    session: Session,
    *,
    check_run: CheckRun,
    project: Project,
    score_result: ScoreResult | None,
    settings: Settings | None = None,
) -> list[Alert]:
    """배포 트리거 검사가 최종 수렴했을 때 웹훅 요약 알림을 1회 생성한다.

    연결된 시나리오 실행이 아직 종료되지 않았다면 생성하지 않고, 시나리오가
    끝난 뒤의 재수렴 호출에서 생성된다. 웹훅 URL이 없는 프로젝트는 건너뛴다.
    """
    if check_run.trigger_source != DEPLOY_TRIGGER_SOURCE:
        return []

    if check_run.status not in TERMINAL_SUMMARY_STATUSES:
        return []

    if not project.alert_webhook_url:
        return []

    if has_unfinished_scenario_runs(session, check_run_id=check_run.id):
        return []

    if deploy_summary_exists(session, check_run_id=check_run.id):
        return []

    runtime_settings = settings or get_settings()
    comparison = run_comparison_service.get_run_comparison(session, check_run_id=check_run.id)
    subject = build_deploy_summary_subject(
        project=project,
        check_run=check_run,
        score_result=score_result,
    )
    body = build_deploy_summary_body(
        project=project,
        check_run=check_run,
        score_result=score_result,
        comparison=comparison,
        web_base_url=runtime_settings.web_base_url,
    )

    alert = Alert(
        project_id=project.id,
        incident_id=None,
        check_run_id=check_run.id,
        alert_type=AlertType.DEPLOY_SUMMARY.value,
        trigger_type=DEPLOY_SUMMARY_TRIGGER_TYPE,
        channel=AlertChannel.WEBHOOK.value,
        status=AlertStatus.PENDING.value,
        recipient_email=None,
        subject=subject,
        body=body,
        delivery_attempts=0,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return [alert]


def build_deploy_summary_subject(
    *,
    project: Project,
    check_run: CheckRun,
    score_result: ScoreResult | None,
) -> str:
    ref_suffix = f" ({check_run.deploy_ref})" if check_run.deploy_ref else ""

    if check_run.status == CheckRunStatus.FAILED.value or score_result is None:
        subject = f"[AIM] {project.name}: 배포 검사 실패{ref_suffix}"
    else:
        risk_label = RISK_KO.get(score_result.deployment_risk, score_result.deployment_risk)
        subject = (
            f"[AIM] {project.name}: 배포 검사 완료 — "
            f"{score_result.overall_score}점 {score_result.grade} · {risk_label}{ref_suffix}"
        )

    return subject[:SUMMARY_SUBJECT_MAX_LENGTH]


def build_deploy_summary_body(
    *,
    project: Project,
    check_run: CheckRun,
    score_result: ScoreResult | None,
    comparison: RunComparison | None,
    web_base_url: str | None,
) -> str:
    lines = [
        f"프로젝트: {project.name}",
        f"배포 참조: {check_run.deploy_ref or '없음'}",
    ]

    if score_result is not None:
        risk_label = RISK_KO.get(score_result.deployment_risk, score_result.deployment_risk)
        lines.append(
            f"결과: {score_result.overall_score}점 · 등급 {score_result.grade} · {risk_label}"
        )
        if score_result.gate_reason:
            lines.append(f"게이트: {score_result.gate_reason}")
    else:
        lines.append("결과: 점수 미산출")

    if check_run.status == CheckRunStatus.FAILED.value:
        lines.append(f"실패 사유: {check_run.failure_reason or '기록되지 않음'}")

    comparison_line = build_comparison_line(comparison)
    if comparison_line:
        lines.append(comparison_line)

    if web_base_url:
        base = web_base_url.rstrip("/")
        lines.append(f"결과 페이지: {base}/projects/{project.id}/check-runs/{check_run.id}")

    return "\n".join(lines)


def build_comparison_line(comparison: RunComparison | None) -> str | None:
    if comparison is None:
        return None

    parts: list[str] = []

    if comparison.overall_score_delta is not None and comparison.overall_score_delta != 0:
        parts.append(f"종합 {format_delta(comparison.overall_score_delta)}")

    if comparison.response_time_delta_ms is not None and comparison.response_time_delta_ms != 0:
        parts.append(f"응답 시간 {format_delta(comparison.response_time_delta_ms)}ms")

    if not parts:
        return "직전 대비: 변화 없음"

    return "직전 대비: " + " · ".join(parts)


def format_delta(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)
