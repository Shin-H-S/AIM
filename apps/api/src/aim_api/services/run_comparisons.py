from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
)

PREVIOUS_RUN_COMPARISON_TYPE = "previous_run"
BASELINE_COMPARISON_TYPE = "baseline"


class BaselineComparisonError(Exception):
    """Base error for explicit baseline-versus-target comparisons."""


class BaselineNotConfiguredError(BaselineComparisonError):
    """Raised when no baseline check run is configured or requested."""


class BaselineCheckRunMissingError(BaselineComparisonError):
    """Raised when the baseline check run does not exist for the project."""


class BaselineComparisonNotAvailableError(BaselineComparisonError):
    """Raised when either run lacks the score result required for comparison."""


@dataclass(frozen=True)
class ComparisonMetrics:
    overall_score_delta: int
    availability_score_delta: int | None
    web_performance_score_delta: int | None
    accessibility_score_delta: int | None
    seo_basic_quality_score_delta: int | None
    response_time_delta_ms: int | None
    performance_score_delta: int | None
    deployment_risk_changed: bool
    summary: str


@dataclass(frozen=True)
class BaselineComparison:
    check_run_id: UUID
    baseline_check_run_id: UUID
    comparison_type: str
    overall_score_delta: int
    availability_score_delta: int | None
    web_performance_score_delta: int | None
    accessibility_score_delta: int | None
    seo_basic_quality_score_delta: int | None
    response_time_delta_ms: int | None
    performance_score_delta: int | None
    current_deployment_risk: str
    baseline_deployment_risk: str
    deployment_risk_changed: bool
    summary: str


def build_comparison_metrics(
    *,
    current_score_result: ScoreResult,
    baseline_score_result: ScoreResult,
    current_availability_result: AvailabilityResult | None,
    baseline_availability_result: AvailabilityResult | None,
    current_lighthouse_result: LighthouseResult | None,
    baseline_lighthouse_result: LighthouseResult | None,
) -> ComparisonMetrics:
    overall_score_delta = diff(
        current_score_result.overall_score,
        baseline_score_result.overall_score,
    )
    response_time_delta_ms = diff_optional(
        current_availability_result.response_time_ms
        if current_availability_result is not None
        else None,
        baseline_availability_result.response_time_ms
        if baseline_availability_result is not None
        else None,
    )
    deployment_risk_changed = (
        current_score_result.deployment_risk != baseline_score_result.deployment_risk
    )
    return ComparisonMetrics(
        overall_score_delta=overall_score_delta,
        availability_score_delta=diff_optional(
            current_score_result.availability_score,
            baseline_score_result.availability_score,
        ),
        web_performance_score_delta=diff_optional(
            current_score_result.web_performance_score,
            baseline_score_result.web_performance_score,
        ),
        accessibility_score_delta=diff_optional(
            current_score_result.accessibility_score,
            baseline_score_result.accessibility_score,
        ),
        seo_basic_quality_score_delta=diff_optional(
            current_score_result.seo_basic_quality_score,
            baseline_score_result.seo_basic_quality_score,
        ),
        response_time_delta_ms=response_time_delta_ms,
        performance_score_delta=diff_optional(
            current_lighthouse_result.performance_score
            if current_lighthouse_result is not None
            else None,
            baseline_lighthouse_result.performance_score
            if baseline_lighthouse_result is not None
            else None,
        ),
        deployment_risk_changed=deployment_risk_changed,
        summary=summarize_comparison(
            overall_score_delta=overall_score_delta,
            response_time_delta_ms=response_time_delta_ms,
            deployment_risk_changed=deployment_risk_changed,
            current_deployment_risk=current_score_result.deployment_risk,
            baseline_deployment_risk=baseline_score_result.deployment_risk,
        ),
    )


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

    metrics = build_comparison_metrics(
        current_score_result=current_score_result,
        baseline_score_result=baseline_score_result,
        current_availability_result=current_availability_result,
        baseline_availability_result=baseline_availability_result,
        current_lighthouse_result=current_lighthouse_result,
        baseline_lighthouse_result=baseline_lighthouse_result,
    )

    comparison = get_run_comparison(session, check_run_id=check_run.id)
    if comparison is None:
        comparison = RunComparison(check_run_id=check_run.id)
        session.add(comparison)

    comparison.baseline_check_run_id = baseline_check_run.id
    comparison.comparison_type = PREVIOUS_RUN_COMPARISON_TYPE
    comparison.overall_score_delta = metrics.overall_score_delta
    comparison.availability_score_delta = metrics.availability_score_delta
    comparison.web_performance_score_delta = metrics.web_performance_score_delta
    comparison.accessibility_score_delta = metrics.accessibility_score_delta
    comparison.seo_basic_quality_score_delta = metrics.seo_basic_quality_score_delta
    comparison.response_time_delta_ms = metrics.response_time_delta_ms
    comparison.performance_score_delta = metrics.performance_score_delta
    comparison.deployment_risk_changed = metrics.deployment_risk_changed
    comparison.summary = metrics.summary
    session.commit()
    session.refresh(comparison)
    return comparison


def compute_baseline_comparison(
    session: Session,
    *,
    project: Project,
    check_run: CheckRun,
    baseline_check_run_id: UUID | None = None,
) -> BaselineComparison:
    """Compare a check run against an explicit baseline without persisting the result.

    The baseline defaults to the project's pinned baseline check run and can be
    overridden per request.
    """
    resolved_baseline_id = baseline_check_run_id or project.baseline_check_run_id
    if resolved_baseline_id is None:
        raise BaselineNotConfiguredError

    baseline_check_run = session.get(CheckRun, resolved_baseline_id)
    if baseline_check_run is None or baseline_check_run.project_id != project.id:
        raise BaselineCheckRunMissingError

    current_score_result = get_score_result(session, check_run_id=check_run.id)
    baseline_score_result = get_score_result(session, check_run_id=baseline_check_run.id)
    if current_score_result is None or baseline_score_result is None:
        raise BaselineComparisonNotAvailableError

    metrics = build_comparison_metrics(
        current_score_result=current_score_result,
        baseline_score_result=baseline_score_result,
        current_availability_result=get_availability_result(session, check_run_id=check_run.id),
        baseline_availability_result=get_availability_result(
            session,
            check_run_id=baseline_check_run.id,
        ),
        current_lighthouse_result=get_lighthouse_result(session, check_run_id=check_run.id),
        baseline_lighthouse_result=get_lighthouse_result(
            session,
            check_run_id=baseline_check_run.id,
        ),
    )
    return BaselineComparison(
        check_run_id=check_run.id,
        baseline_check_run_id=baseline_check_run.id,
        comparison_type=BASELINE_COMPARISON_TYPE,
        overall_score_delta=metrics.overall_score_delta,
        availability_score_delta=metrics.availability_score_delta,
        web_performance_score_delta=metrics.web_performance_score_delta,
        accessibility_score_delta=metrics.accessibility_score_delta,
        seo_basic_quality_score_delta=metrics.seo_basic_quality_score_delta,
        response_time_delta_ms=metrics.response_time_delta_ms,
        performance_score_delta=metrics.performance_score_delta,
        current_deployment_risk=current_score_result.deployment_risk,
        baseline_deployment_risk=baseline_score_result.deployment_risk,
        deployment_risk_changed=metrics.deployment_risk_changed,
        summary=metrics.summary,
    )


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
