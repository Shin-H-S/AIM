from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.schemas.ai_diagnosis import (
    AI_DIAGNOSIS_INPUT_SCHEMA_VERSION,
    AIDiagnosisEvidenceItem,
    AIDiagnosisEvidenceKind,
    AIDiagnosisInput,
    AIDiagnosisRunContext,
    AIDiagnosisSeverity,
    AIDiagnosisStatement,
    AIDiagnosisStatementType,
)
from aim_api.schemas.check_run import CheckRunRead, ScoreResultRead
from pydantic import ValidationError


def check_run_payload(project_id: UUID, check_run_id: UUID, user_id: UUID) -> CheckRunRead:
    return CheckRunRead.model_validate(
        {
            "id": check_run_id,
            "project_id": project_id,
            "requested_by_id": user_id,
            "status": "COMPLETED",
            "trigger_source": "manual",
            "failure_reason": None,
            "queued_at": datetime(2026, 6, 29, 0, 0, tzinfo=UTC),
            "started_at": datetime(2026, 6, 29, 0, 1, tzinfo=UTC),
            "finished_at": datetime(2026, 6, 29, 0, 2, tzinfo=UTC),
            "created_at": datetime(2026, 6, 29, 0, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 29, 0, 2, tzinfo=UTC),
        }
    )


def score_result_payload() -> ScoreResultRead:
    return ScoreResultRead.model_validate(
        {
            "availability_score": 100,
            "functional_stability_score": 0,
            "web_performance_score": 80,
            "accessibility_score": 90,
            "seo_basic_quality_score": 90,
            "regression_stability_score": None,
            "overall_score": 72,
            "evaluated_weight": 90,
            "grade": "D",
            "deployment_risk": "RISK",
            "gate_reason": "Critical scenario run failed.",
            "scoring_version": "2026-06-28.scenario-v1",
            "created_at": datetime(2026, 6, 29, 0, 3, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 29, 0, 3, tzinfo=UTC),
        }
    )


def test_ai_diagnosis_input_accepts_structured_scan_context() -> None:
    project_id = uuid4()
    check_run_id = uuid4()
    user_id = uuid4()

    payload = AIDiagnosisInput(
        run_context=AIDiagnosisRunContext(
            project_id=project_id,
            check_run_id=check_run_id,
            generated_at=datetime(2026, 6, 29, 0, 4, tzinfo=UTC),
            service_url="https://example.com",
            environment="production",
        ),
        check_run=check_run_payload(project_id, check_run_id, user_id),
        score_result=score_result_payload(),
        evidence_items=[
            AIDiagnosisEvidenceItem(
                id="score-risk-gate",
                kind=AIDiagnosisEvidenceKind.SCORE_RESULT,
                source_id=check_run_id,
                summary="Deterministic scoring marked the deployment as RISK.",
                details={
                    "grade": "D",
                    "deployment_risk": "RISK",
                    "gate_reason": "Critical scenario run failed.",
                },
            )
        ],
        statements=[
            AIDiagnosisStatement(
                id="critical-scenario-risk",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK,
                category="functional_stability",
                summary="A critical scenario failure made this deployment risky.",
                evidence_ids=["score-risk-gate"],
            ),
            AIDiagnosisStatement(
                id="root-cause-unknown",
                statement_type=AIDiagnosisStatementType.UNKNOWN_CAUSE,
                severity=AIDiagnosisSeverity.WARNING,
                category="unknown_cause",
                summary="The external scan did not collect internal server logs.",
                unknown_reason="Only browser and network evidence is available.",
            ),
        ],
    )

    dumped = payload.model_dump(mode="json")

    assert dumped["schema_version"] == AI_DIAGNOSIS_INPUT_SCHEMA_VERSION
    assert dumped["run_context"]["service_url"] == "https://example.com"
    assert dumped["score_result"]["deployment_risk"] == "RISK"
    assert dumped["evidence_items"][0]["id"] == "score-risk-gate"
    assert dumped["statements"][0]["statement_type"] == "confirmed_observation"
    assert payload.generation_rules[0].startswith("Use deterministic score_result")


def test_confirmed_observation_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="must reference evidence"):
        AIDiagnosisStatement(
            id="missing-evidence",
            statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
            severity=AIDiagnosisSeverity.RISK,
            category="availability",
            summary="The service was unavailable.",
            evidence_ids=[],
        )


def test_unknown_cause_requires_reason() -> None:
    with pytest.raises(ValidationError, match="must explain why the cause is unknown"):
        AIDiagnosisStatement(
            id="unknown-without-reason",
            statement_type=AIDiagnosisStatementType.UNKNOWN_CAUSE,
            severity=AIDiagnosisSeverity.WARNING,
            category="unknown_cause",
            summary="The root cause cannot be confirmed from external evidence.",
        )


def test_ai_diagnosis_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AIDiagnosisEvidenceItem.model_validate(
            {
                "id": "network-failure",
                "kind": AIDiagnosisEvidenceKind.NETWORK_FAILURE,
                "summary": "A request failed.",
                "unexpected_secret": "do-not-accept",
            }
        )
