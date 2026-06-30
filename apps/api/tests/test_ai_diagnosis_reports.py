from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisDeploymentRisk,
    AIDiagnosisEvidenceItem,
    AIDiagnosisEvidenceKind,
    AIDiagnosisInput,
    AIDiagnosisRunContext,
    AIDiagnosisSeverity,
    AIDiagnosisStatement,
    AIDiagnosisStatementType,
)
from aim_api.schemas.check_run import CheckRunRead, RunComparisonRead, ScoreResultRead
from aim_api.services.ai_diagnosis_reports import (
    AIDiagnosisReportGenerationError,
    build_ai_diagnosis_report,
)


def check_run_payload(project_id: UUID, check_run_id: UUID, user_id: UUID) -> CheckRunRead:
    return CheckRunRead.model_validate(
        {
            "id": check_run_id,
            "project_id": project_id,
            "requested_by_id": user_id,
            "status": "COMPLETED",
            "trigger_source": "manual",
            "failure_reason": None,
            "queued_at": datetime(2026, 6, 30, 0, 0, tzinfo=UTC),
            "started_at": datetime(2026, 6, 30, 0, 1, tzinfo=UTC),
            "finished_at": datetime(2026, 6, 30, 0, 2, tzinfo=UTC),
            "created_at": datetime(2026, 6, 30, 0, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 30, 0, 2, tzinfo=UTC),
        }
    )


def score_result_payload(
    *,
    deployment_risk: str = "RISK",
    grade: str = "D",
    overall_score: int = 55,
) -> ScoreResultRead:
    return ScoreResultRead.model_validate(
        {
            "availability_score": 100,
            "functional_stability_score": 0,
            "web_performance_score": 80,
            "accessibility_score": 90,
            "seo_basic_quality_score": 90,
            "regression_stability_score": None,
            "overall_score": overall_score,
            "evaluated_weight": 90,
            "grade": grade,
            "deployment_risk": deployment_risk,
            "gate_reason": "Critical scenario run failed.",
            "scoring_version": "2026-06-28.scenario-v1",
            "created_at": datetime(2026, 6, 30, 0, 3, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 30, 0, 3, tzinfo=UTC),
        }
    )


def comparison_payload(check_run_id: UUID) -> RunComparisonRead:
    return RunComparisonRead.model_validate(
        {
            "baseline_check_run_id": check_run_id,
            "comparison_type": "previous_run",
            "overall_score_delta": -20,
            "availability_score_delta": 0,
            "web_performance_score_delta": 0,
            "accessibility_score_delta": 8,
            "seo_basic_quality_score_delta": 0,
            "response_time_delta_ms": -100,
            "performance_score_delta": None,
            "deployment_risk_changed": True,
            "summary": "Overall score regressed by 20.",
            "created_at": datetime(2026, 6, 30, 0, 4, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 30, 0, 4, tzinfo=UTC),
        }
    )


def diagnosis_input_payload(
    *,
    score_result: ScoreResultRead | None = None,
    include_score_evidence: bool = True,
    comparison_result: RunComparisonRead | None = None,
    statements: list[AIDiagnosisStatement] | None = None,
) -> AIDiagnosisInput:
    project_id = uuid4()
    check_run_id = uuid4()
    evidence_items = [
        AIDiagnosisEvidenceItem(
            id="check-run-status",
            kind=AIDiagnosisEvidenceKind.CHECK_RUN,
            summary="CheckRun status is COMPLETED.",
        )
    ]
    if include_score_evidence:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="score-result",
                kind=AIDiagnosisEvidenceKind.SCORE_RESULT,
                summary="Deterministic scoring marked this run as RISK.",
            )
        )
    if comparison_result is not None:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="run-comparison",
                kind=AIDiagnosisEvidenceKind.RUN_COMPARISON,
                summary="Comparison with previous run was collected.",
            )
        )

    return AIDiagnosisInput(
        run_context=AIDiagnosisRunContext(
            project_id=project_id,
            check_run_id=check_run_id,
            generated_at=datetime(2026, 6, 30, 0, 5, tzinfo=UTC),
            service_url="https://example.com",
            environment="production",
        ),
        check_run=check_run_payload(project_id, check_run_id, uuid4()),
        score_result=score_result,
        comparison_result=comparison_result,
        evidence_items=evidence_items,
        statements=statements
        if statements is not None
        else [
            AIDiagnosisStatement(
                id="functional-risk",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK,
                category="functional_stability",
                summary="A linked critical ScenarioRun failed.",
                evidence_ids=["scenario-run-failed"],
            )
        ],
    )


def test_build_ai_diagnosis_report_prioritizes_risk_statements_and_changes() -> None:
    check_run_id = uuid4()
    diagnosis_input = diagnosis_input_payload(
        score_result=score_result_payload(),
        comparison_result=comparison_payload(check_run_id),
        statements=[
            AIDiagnosisStatement(
                id="availability-warning",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.WARNING,
                category="availability",
                summary="Response time exceeded the configured threshold.",
                evidence_ids=["availability-result"],
            ),
            AIDiagnosisStatement(
                id="functional-risk",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK,
                category="functional_stability",
                summary="A linked critical ScenarioRun failed.",
                evidence_ids=["scenario-run-failed"],
            ),
            AIDiagnosisStatement(
                id="unknown-root-cause",
                statement_type=AIDiagnosisStatementType.UNKNOWN_CAUSE,
                severity=AIDiagnosisSeverity.WARNING,
                category="unknown_cause",
                summary="The root cause cannot be confirmed from external evidence.",
                unknown_reason="Server logs were not collected.",
            ),
        ],
    )

    report = build_ai_diagnosis_report(
        diagnosis_input,
        generated_at=datetime(2026, 6, 30, 0, 6, tzinfo=UTC),
    )

    assert report.project_id == diagnosis_input.run_context.project_id
    assert report.check_run_id == diagnosis_input.run_context.check_run_id
    assert report.score.deployment_risk == AIDiagnosisDeploymentRisk.RISK
    assert [issue.priority for issue in report.top_issues] == [1, 2, 3]
    assert report.top_issues[0].id == "functional-risk"
    assert report.top_issues[0].category == "functional_stability"
    assert report.top_issues[2].statement_type == AIDiagnosisStatementType.UNKNOWN_CAUSE
    assert report.top_issues[2].unknown_reason == "Server logs were not collected."
    assert [change.metric_name for change in report.improved_areas] == [
        "accessibility_score",
        "response_time_ms",
    ]
    assert [change.metric_name for change in report.regressed_areas] == ["overall_score"]
    assert report.generation_warnings == []


def test_build_ai_diagnosis_report_creates_stable_report_without_top_issues() -> None:
    diagnosis_input = diagnosis_input_payload(
        score_result=score_result_payload(
            deployment_risk="STABLE",
            grade="A",
            overall_score=95,
        ),
        statements=[
            AIDiagnosisStatement(
                id="no-risk-evidence",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.INFO,
                category="summary",
                summary="No deterministic risk evidence has been collected yet.",
                evidence_ids=["check-run-status"],
            )
        ],
    )

    report = build_ai_diagnosis_report(diagnosis_input)

    assert report.score.deployment_risk == AIDiagnosisDeploymentRisk.STABLE
    assert report.top_issues == []
    assert report.improved_areas == []
    assert report.regressed_areas == []
    assert report.generation_warnings == [
        "No run comparison was available, so changed areas are empty."
    ]


def test_build_ai_diagnosis_report_uses_score_issue_when_no_warning_statement_exists() -> None:
    diagnosis_input = diagnosis_input_payload(
        score_result=score_result_payload(deployment_risk="WARNING", grade="C", overall_score=72),
        statements=[
            AIDiagnosisStatement(
                id="only-info",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.INFO,
                category="summary",
                summary="Only informational evidence was provided.",
                evidence_ids=["check-run-status"],
            )
        ],
    )

    report = build_ai_diagnosis_report(diagnosis_input)

    assert report.score.deployment_risk == AIDiagnosisDeploymentRisk.WARNING
    assert len(report.top_issues) == 1
    assert report.top_issues[0].id == "deployment-risk-score-result"
    assert report.top_issues[0].evidence_ids == ["score-result"]
    assert (
        "No risk or warning statement was provided, so the report used score evidence."
        in report.generation_warnings
    )


def test_build_ai_diagnosis_report_requires_score_result() -> None:
    diagnosis_input = diagnosis_input_payload(score_result=None)

    with pytest.raises(AIDiagnosisReportGenerationError, match="score_result is required"):
        build_ai_diagnosis_report(diagnosis_input)


def test_build_ai_diagnosis_report_requires_score_evidence() -> None:
    diagnosis_input = diagnosis_input_payload(
        score_result=score_result_payload(),
        include_score_evidence=False,
    )

    with pytest.raises(AIDiagnosisReportGenerationError, match="score_result evidence"):
        build_ai_diagnosis_report(diagnosis_input)
