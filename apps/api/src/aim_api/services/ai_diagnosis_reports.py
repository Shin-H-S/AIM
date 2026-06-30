from datetime import UTC, datetime
from typing import Final, Literal, cast

from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisDeploymentRisk,
    AIDiagnosisEvidenceKind,
    AIDiagnosisInput,
    AIDiagnosisReport,
    AIDiagnosisReportChange,
    AIDiagnosisReportIssue,
    AIDiagnosisReportScore,
    AIDiagnosisSeverity,
    AIDiagnosisStatement,
    AIDiagnosisStatementType,
)
from aim_api.schemas.check_run import ScoreResultRead

ReportGrade = Literal["A", "B", "C", "D", "F"]

SEVERITY_PRIORITY: Final[dict[AIDiagnosisSeverity, int]] = {
    AIDiagnosisSeverity.RISK: 0,
    AIDiagnosisSeverity.WARNING: 1,
    AIDiagnosisSeverity.INFO: 2,
}

ISSUE_IMPACT_BY_CATEGORY: Final[dict[str, str]] = {
    "availability": "Users may be unable to reach the service or may experience unstable access.",
    "browser_console": "Users may encounter client-side errors in the tested browser flow.",
    "check_run": "The scan did not finish cleanly, so release confidence is lower.",
    "deployment_risk": "The deployment may be risky according to deterministic scoring.",
    "functional_stability": "Users may be blocked in a critical browser flow.",
    "network": "The tested flow may fail because browser requests did not complete.",
    "regression": "The latest run is worse than the baseline and should be reviewed.",
    "ssl": "Users may see browser security warnings or failed secure connections.",
    "unknown_cause": "The visible symptom is known, but the root cause is not confirmed.",
    "web_quality": "Users may experience degraded loading quality or incomplete quality checks.",
}

ISSUE_ACTION_BY_CATEGORY: Final[dict[str, str]] = {
    "availability": (
        "Review the availability evidence, recent deploys, and external dependency status."
    ),
    "browser_console": (
        "Inspect the captured console errors and reproduce the browser flow locally."
    ),
    "check_run": "Investigate the CheckRun failure and run the scan again after the fix.",
    "deployment_risk": (
        "Address the deterministic gate reason before treating this deployment as safe."
    ),
    "functional_stability": "Re-run the scenario and inspect the failed step evidence first.",
    "network": "Inspect the failed browser requests and verify the related endpoint behavior.",
    "regression": (
        "Compare this run with the baseline and decide whether the regression is acceptable."
    ),
    "ssl": "Check certificate validity, expiration, and HTTPS configuration.",
    "unknown_cause": (
        "Inspect server logs or telemetry for the same time window and correlate evidence."
    ),
    "web_quality": "Review Lighthouse artifacts and fix the highest-impact diagnostics first.",
}


class AIDiagnosisReportGenerationError(Exception):
    """Raised when a report cannot be generated without inventing evidence."""


def build_ai_diagnosis_report(
    diagnosis_input: AIDiagnosisInput,
    *,
    generated_at: datetime | None = None,
) -> AIDiagnosisReport:
    report_score = build_report_score(diagnosis_input)
    top_issues = build_top_issues(diagnosis_input)
    generation_warnings = build_generation_warnings(diagnosis_input)

    if report_score.deployment_risk != AIDiagnosisDeploymentRisk.STABLE and not top_issues:
        top_issues = [build_score_based_issue(report_score)]
        generation_warnings.append(
            "No risk or warning statement was provided, so the report used score evidence."
        )

    improved_areas, regressed_areas = build_report_changes(diagnosis_input)

    return AIDiagnosisReport(
        input_schema_version=diagnosis_input.schema_version,
        project_id=diagnosis_input.run_context.project_id,
        check_run_id=diagnosis_input.run_context.check_run_id,
        generated_at=generated_at or datetime.now(UTC),
        summary=build_report_summary(report_score, top_issues),
        score=report_score,
        top_issues=top_issues,
        improved_areas=improved_areas,
        regressed_areas=regressed_areas,
        generation_warnings=generation_warnings,
    )


def build_report_score(diagnosis_input: AIDiagnosisInput) -> AIDiagnosisReportScore:
    score_result = diagnosis_input.score_result
    if score_result is None:
        raise AIDiagnosisReportGenerationError(
            "score_result is required to generate an AI diagnosis report."
        )

    evidence_ids = find_evidence_ids(
        diagnosis_input,
        kind=AIDiagnosisEvidenceKind.SCORE_RESULT,
    )
    if not evidence_ids:
        raise AIDiagnosisReportGenerationError(
            "score_result evidence is required to generate an AI diagnosis report."
        )

    return AIDiagnosisReportScore(
        overall_score=score_result.overall_score,
        grade=normalize_grade(score_result.grade),
        deployment_risk=normalize_deployment_risk(score_result),
        gate_reason=score_result.gate_reason,
        evidence_ids=evidence_ids,
    )


def build_top_issues(diagnosis_input: AIDiagnosisInput) -> list[AIDiagnosisReportIssue]:
    issue_statements = [
        statement
        for statement in diagnosis_input.statements
        if statement.severity in {AIDiagnosisSeverity.RISK, AIDiagnosisSeverity.WARNING}
    ]
    issue_statements.sort(key=lambda statement: SEVERITY_PRIORITY[statement.severity])

    return [
        build_report_issue(statement, priority=index)
        for index, statement in enumerate(issue_statements[:20], start=1)
    ]


def build_report_issue(
    statement: AIDiagnosisStatement,
    *,
    priority: int,
) -> AIDiagnosisReportIssue:
    return AIDiagnosisReportIssue(
        id=truncate_text(statement.id, max_length=120),
        priority=priority,
        title=truncate_text(statement.summary.rstrip("."), max_length=200),
        statement_type=statement.statement_type,
        severity=statement.severity,
        category=statement.category,
        summary=statement.summary,
        evidence_ids=statement.evidence_ids,
        expected_user_impact=expected_user_impact_for(statement.category),
        recommended_next_action=recommended_next_action_for(statement.category),
        unknown_reason=statement.unknown_reason,
    )


def build_score_based_issue(report_score: AIDiagnosisReportScore) -> AIDiagnosisReportIssue:
    severity = (
        AIDiagnosisSeverity.RISK
        if report_score.deployment_risk == AIDiagnosisDeploymentRisk.RISK
        else AIDiagnosisSeverity.WARNING
    )
    summary = (
        f"Deterministic scoring marked this run as {report_score.deployment_risk.value} "
        f"with grade {report_score.grade}."
    )
    return AIDiagnosisReportIssue(
        id="deployment-risk-score-result",
        priority=1,
        title="Deployment risk from deterministic score",
        statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
        severity=severity,
        category="deployment_risk",
        summary=summary,
        evidence_ids=report_score.evidence_ids,
        expected_user_impact=expected_user_impact_for("deployment_risk"),
        recommended_next_action=recommended_next_action_for("deployment_risk"),
    )


def build_report_changes(
    diagnosis_input: AIDiagnosisInput,
) -> tuple[list[AIDiagnosisReportChange], list[AIDiagnosisReportChange]]:
    comparison = diagnosis_input.comparison_result
    if comparison is None:
        return [], []

    evidence_ids = find_evidence_ids(
        diagnosis_input,
        kind=AIDiagnosisEvidenceKind.RUN_COMPARISON,
    )
    if not evidence_ids:
        return [], []

    metrics: tuple[tuple[str, str, int | None, bool], ...] = (
        ("overall_score", "Overall score", comparison.overall_score_delta, True),
        ("availability_score", "Availability score", comparison.availability_score_delta, True),
        (
            "web_performance_score",
            "Web performance score",
            comparison.web_performance_score_delta,
            True,
        ),
        (
            "accessibility_score",
            "Accessibility score",
            comparison.accessibility_score_delta,
            True,
        ),
        (
            "seo_basic_quality_score",
            "SEO and basic quality score",
            comparison.seo_basic_quality_score_delta,
            True,
        ),
        ("response_time_ms", "Response time", comparison.response_time_delta_ms, False),
        (
            "performance_score",
            "Lighthouse performance score",
            comparison.performance_score_delta,
            True,
        ),
    )

    improved_areas: list[AIDiagnosisReportChange] = []
    regressed_areas: list[AIDiagnosisReportChange] = []
    for metric_name, label, delta, higher_is_better in metrics:
        if delta is None or delta == 0:
            continue

        is_improvement = delta > 0 if higher_is_better else delta < 0
        change = build_report_change(
            metric_name=metric_name,
            label=label,
            delta=delta,
            evidence_ids=evidence_ids,
            is_improvement=is_improvement,
        )
        if is_improvement:
            improved_areas.append(change)
        else:
            regressed_areas.append(change)

    return improved_areas[:20], regressed_areas[:20]


def build_report_change(
    *,
    metric_name: str,
    label: str,
    delta: int,
    evidence_ids: list[str],
    is_improvement: bool,
) -> AIDiagnosisReportChange:
    direction = "improved" if is_improvement else "regressed"
    unit = " ms" if metric_name == "response_time_ms" else ""
    return AIDiagnosisReportChange(
        id=f"{metric_name}-{direction}",
        category="regression",
        summary=f"{label} {direction} by {abs(delta)}{unit} compared with the baseline.",
        evidence_ids=evidence_ids,
        metric_name=metric_name,
        delta=delta,
    )


def build_generation_warnings(diagnosis_input: AIDiagnosisInput) -> list[str]:
    warnings: list[str] = []
    if diagnosis_input.comparison_result is None:
        warnings.append("No run comparison was available, so changed areas are empty.")
    elif not find_evidence_ids(diagnosis_input, kind=AIDiagnosisEvidenceKind.RUN_COMPARISON):
        warnings.append("Run comparison existed, but no comparison evidence item was provided.")

    return warnings


def build_report_summary(
    report_score: AIDiagnosisReportScore,
    top_issues: list[AIDiagnosisReportIssue],
) -> str:
    score_summary = (
        f"This run is marked as {report_score.deployment_risk.value} with grade "
        f"{report_score.grade} and score {report_score.overall_score}/100."
    )
    if report_score.deployment_risk == AIDiagnosisDeploymentRisk.STABLE:
        return f"{score_summary} No top deployment issues were identified from evidence."

    if top_issues:
        return f"{score_summary} Highest priority: {top_issues[0].title}."

    return f"{score_summary} No top issue statement was available."


def find_evidence_ids(
    diagnosis_input: AIDiagnosisInput,
    *,
    kind: AIDiagnosisEvidenceKind,
) -> list[str]:
    return [item.id for item in diagnosis_input.evidence_items if item.kind == kind][:20]


def normalize_deployment_risk(score_result: ScoreResultRead) -> AIDiagnosisDeploymentRisk:
    try:
        return AIDiagnosisDeploymentRisk(score_result.deployment_risk)
    except ValueError as exc:
        raise AIDiagnosisReportGenerationError(
            f"Unsupported deployment risk: {score_result.deployment_risk}"
        ) from exc


def normalize_grade(grade: str) -> ReportGrade:
    if grade not in {"A", "B", "C", "D", "F"}:
        raise AIDiagnosisReportGenerationError(f"Unsupported report grade: {grade}")

    return cast(ReportGrade, grade)


def expected_user_impact_for(category: str) -> str:
    return ISSUE_IMPACT_BY_CATEGORY.get(
        category,
        "The affected user experience should be reviewed before deployment.",
    )


def recommended_next_action_for(category: str) -> str:
    return ISSUE_ACTION_BY_CATEGORY.get(
        category,
        "Review the referenced evidence and address the highest-impact issue first.",
    )


def truncate_text(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    return f"{value[: max_length - 3]}..."
