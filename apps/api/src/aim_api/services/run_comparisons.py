from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.scanner_result import (
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
)

PREVIOUS_RUN_COMPARISON_TYPE = "previous_run"


def record_previous_run_comparison(
    session: Session,
    *,
    check_run: CheckRun,
    current_score_result: ScoreResult,
    current_availability_result: AvailabilityResult | None,
    current_lighthouse_result: LighthouseResult | None,
) -> RunComparison | None:
    baseline_check_run = get_previous_comparable_check_run(
        session,
        project_id=check_run.project_id,
        check_run_id=check_run.id,
    )
    if baseline_check_run is None:
        return None

    baseline_score_result = get_score_result(
        session,
        check_run_id=baseline_check_run.id,
    )
    if baseline_score_result is None:
        return None

    baseline_availability_result = get_availability_result(
        session,
        check_run_id=baseline_check_run.id,
    )
    baseline_lighthouse_result = get_lighthouse_result(
        session,
        check_run_id=baseline_check_run.id,
    )

    comparison = get_run_comparison(session, check_run_id=check_run.id)
    if comparison is None:
        comparison = RunComparison(check_run_id=check_run.id)
        session.add(comparison)

    comparison.baseline_check_run_id = baseline_check_run.id
    comparison.comparison_type = PREVIOUS_RUN_COMPARISON_TYPE
    comparison.overall_score_delta = diff(
        current_score_result.overall_score,
        baseline_score_result.overall_score,
    )
    comparison.availability_score_delta = diff_optional(
        current_score_result.availability_score,
        baseline_score_result.availability_score,
    )
    comparison.web_performance_score_delta = diff_optional(
        current_score_result.web_performance_score,
        baseline_score_result.web_performance_score,
    )
    comparison.accessibility_score_delta = diff_optional(
        current_score_result.accessibility_score,
        baseline_score_result.accessibility_score,
    )
    comparison.seo_basic_quality_score_delta = diff_optional(
        current_score_result.seo_basic_quality_score,
        baseline_score_result.seo_basic_quality_score,
    )
    comparison.response_time_delta_ms = diff_optional(
        current_availability_result.response_time_ms
        if current_availability_result is not None
        else None,
        baseline_availability_result.response_time_ms
        if baseline_availability_result is not None
        else None,
    )
    comparison.performance_score_delta = diff_optional(
        current_lighthouse_result.performance_score
        if current_lighthouse_result is not None
        else None,
        baseline_lighthouse_result.performance_score
        if baseline_lighthouse_result is not None
        else None,
    )
    comparison.deployment_risk_changed = (
        current_score_result.deployment_risk != baseline_score_result.deployment_risk
    )
    comparison.summary = summarize_comparison(
        overall_score_delta=comparison.overall_score_delta,
        response_time_delta_ms=comparison.response_time_delta_ms,
        deployment_risk_changed=comparison.deployment_risk_changed,
        current_deployment_risk=current_score_result.deployment_risk,
        baseline_deployment_risk=baseline_score_result.deployment_risk,
    )
    session.commit()
    session.refresh(comparison)
    return comparison


def get_previous_comparable_check_run(
    session: Session,
    *,
    project_id: UUID,
    check_run_id: UUID,
) -> CheckRun | None:
    current_check_run = session.get(CheckRun, check_run_id)
    if current_check_run is None:
        return None

    terminal_statuses = [
        CheckRunStatus.COMPLETED.value,
        CheckRunStatus.FAILED.value,
        CheckRunStatus.CANCELLED.value,
    ]
    return session.scalar(
        select(CheckRun)
        .join(ScoreResult, ScoreResult.check_run_id == CheckRun.id)
        .where(
            CheckRun.project_id == project_id,
            CheckRun.id != check_run_id,
            CheckRun.status.in_(terminal_statuses),
            CheckRun.created_at < current_check_run.created_at,
        )
        .order_by(CheckRun.created_at.desc(), CheckRun.id.desc())
        .limit(1)
    )


def get_run_comparison(
    session: Session,
    *,
    check_run_id: UUID,
) -> RunComparison | None:
    return session.scalar(select(RunComparison).where(RunComparison.check_run_id == check_run_id))


def get_score_result(session: Session, *, check_run_id: UUID) -> ScoreResult | None:
    return session.scalar(select(ScoreResult).where(ScoreResult.check_run_id == check_run_id))


def get_availability_result(
    session: Session,
    *,
    check_run_id: UUID,
) -> AvailabilityResult | None:
    return session.scalar(
        select(AvailabilityResult).where(AvailabilityResult.check_run_id == check_run_id)
    )


def get_lighthouse_result(
    session: Session,
    *,
    check_run_id: UUID,
) -> LighthouseResult | None:
    return session.scalar(
        select(LighthouseResult).where(LighthouseResult.check_run_id == check_run_id)
    )


def diff(current_value: int, baseline_value: int) -> int:
    return current_value - baseline_value


def diff_optional(current_value: int | None, baseline_value: int | None) -> int | None:
    if current_value is None or baseline_value is None:
        return None

    return current_value - baseline_value


def summarize_comparison(
    *,
    overall_score_delta: int | None,
    response_time_delta_ms: int | None,
    deployment_risk_changed: bool,
    current_deployment_risk: str,
    baseline_deployment_risk: str,
) -> str:
    parts: list[str] = []
    if overall_score_delta is not None:
        if overall_score_delta > 0:
            parts.append(f"Overall score improved by {overall_score_delta}.")
        elif overall_score_delta < 0:
            parts.append(f"Overall score regressed by {abs(overall_score_delta)}.")
        else:
            parts.append("Overall score did not change.")

    if response_time_delta_ms is not None:
        if response_time_delta_ms > 0:
            parts.append(f"Response time slowed by {response_time_delta_ms}ms.")
        elif response_time_delta_ms < 0:
            parts.append(f"Response time improved by {abs(response_time_delta_ms)}ms.")

    if deployment_risk_changed:
        parts.append(
            f"Deployment risk changed from {baseline_deployment_risk} to {current_deployment_risk}."
        )

    return " ".join(parts) if parts else "No comparable metric changes were detected."
