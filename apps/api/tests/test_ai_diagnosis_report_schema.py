from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.schemas.ai_diagnosis import (
    AI_DIAGNOSIS_INPUT_SCHEMA_VERSION,
    AI_DIAGNOSIS_REPORT_SCHEMA_VERSION,
    AIDiagnosisDeploymentRisk,
    AIDiagnosisReport,
    AIDiagnosisReportChange,
    AIDiagnosisReportIssue,
    AIDiagnosisReportScore,
    AIDiagnosisSeverity,
    AIDiagnosisStatementType,
)
from pydantic import ValidationError


def score_summary(
    *,
    deployment_risk: AIDiagnosisDeploymentRisk = AIDiagnosisDeploymentRisk.RISK,
) -> AIDiagnosisReportScore:
    return AIDiagnosisReportScore(
        overall_score=55,
        grade="D",
        deployment_risk=deployment_risk,
        gate_reason="Critical scenario run failed.",
        evidence_ids=["score-result"],
    )


def top_issue(
    *, priority: int = 1, issue_id: str = "critical-login-failure"
) -> AIDiagnosisReportIssue:
    return AIDiagnosisReportIssue(
        id=issue_id,
        priority=priority,
        title="Critical login flow failed",
        statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
        severity=AIDiagnosisSeverity.RISK,
        category="functional_stability",
        summary="The linked critical login ScenarioRun failed.",
        evidence_ids=["scenario-run-failed", "failed-step"],
        expected_user_impact="Users may be unable to sign in after deployment.",
        recommended_next_action=(
            "Reproduce the login scenario and fix the failing selector or app state."
        ),
    )


def report_payload(
    *,
    project_id: UUID | None = None,
    check_run_id: UUID | None = None,
    score: AIDiagnosisReportScore | None = None,
    top_issues: list[AIDiagnosisReportIssue] | None = None,
) -> AIDiagnosisReport:
    return AIDiagnosisReport(
        project_id=project_id or uuid4(),
        check_run_id=check_run_id or uuid4(),
        generated_at=datetime(2026, 6, 30, 0, 0, tzinfo=UTC),
        summary="The deployment is risky because a critical user flow failed.",
        score=score or score_summary(),
        top_issues=[top_issue()] if top_issues is None else top_issues,
        improved_areas=[
            AIDiagnosisReportChange(
                id="accessibility-improved",
                category="accessibility",
                summary="Accessibility score improved compared with the previous run.",
                evidence_ids=["run-comparison"],
                metric_name="accessibility_score",
                previous_value=82,
                current_value=90,
                delta=8,
            )
        ],
        regressed_areas=[
            AIDiagnosisReportChange(
                id="overall-score-regressed",
                category="regression",
                summary="Overall score decreased compared with the previous run.",
                evidence_ids=["run-comparison"],
                metric_name="overall_score",
                previous_value=75,
                current_value=55,
                delta=-20,
            )
        ],
    )


def test_ai_diagnosis_report_accepts_evidence_based_output() -> None:
    report = report_payload()

    dumped = report.model_dump(mode="json")

    assert dumped["schema_version"] == AI_DIAGNOSIS_REPORT_SCHEMA_VERSION
    assert dumped["input_schema_version"] == AI_DIAGNOSIS_INPUT_SCHEMA_VERSION
    assert dumped["score"]["deployment_risk"] == "RISK"
    assert dumped["top_issues"][0]["statement_type"] == "confirmed_observation"
    assert dumped["top_issues"][0]["evidence_ids"] == [
        "scenario-run-failed",
        "failed-step",
    ]
    assert dumped["improved_areas"][0]["metric_name"] == "accessibility_score"
    assert dumped["regressed_areas"][0]["delta"] == -20


def test_stable_ai_diagnosis_report_may_have_no_top_issues() -> None:
    report = report_payload(
        score=AIDiagnosisReportScore(
            overall_score=95,
            grade="A",
            deployment_risk=AIDiagnosisDeploymentRisk.STABLE,
            gate_reason=None,
            evidence_ids=["score-result"],
        ),
        top_issues=[],
    )

    assert report.score.deployment_risk == AIDiagnosisDeploymentRisk.STABLE
    assert report.top_issues == []


def test_warning_or_risk_ai_diagnosis_report_requires_top_issue() -> None:
    with pytest.raises(ValidationError, match="must include at least one top issue"):
        report_payload(top_issues=[])


def test_report_issue_requires_evidence_for_observations_and_inferences() -> None:
    with pytest.raises(ValidationError, match="must reference evidence"):
        AIDiagnosisReportIssue(
            id="missing-evidence",
            priority=1,
            title="Availability failure",
            statement_type=AIDiagnosisStatementType.EVIDENCE_BASED_INFERENCE,
            severity=AIDiagnosisSeverity.RISK,
            category="availability",
            summary="The service may be unavailable.",
            evidence_ids=[],
            expected_user_impact="Users may not be able to open the service.",
            recommended_next_action="Check the failing availability evidence first.",
        )


def test_unknown_report_issue_requires_unknown_reason() -> None:
    with pytest.raises(ValidationError, match="must explain why the cause is unknown"):
        AIDiagnosisReportIssue(
            id="unknown-cause",
            priority=1,
            title="Root cause cannot be confirmed",
            statement_type=AIDiagnosisStatementType.UNKNOWN_CAUSE,
            severity=AIDiagnosisSeverity.WARNING,
            category="unknown_cause",
            summary="External checks did not collect server logs.",
            expected_user_impact="The user-visible impact is known, but the server cause is not.",
            recommended_next_action="Inspect application logs for the same time window.",
        )


def test_top_issue_priorities_must_be_unique_and_ordered() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        report_payload(
            top_issues=[
                top_issue(priority=1, issue_id="first"),
                top_issue(priority=1, issue_id="duplicate"),
            ]
        )

    with pytest.raises(ValidationError, match="ordered by priority"):
        report_payload(
            top_issues=[
                top_issue(priority=2, issue_id="second"),
                top_issue(priority=1, issue_id="first"),
            ]
        )
