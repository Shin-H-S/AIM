from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.config import Settings
from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisDeploymentRisk,
    AIDiagnosisInput,
    AIDiagnosisReport,
    AIDiagnosisReportIssue,
    AIDiagnosisReportScore,
    AIDiagnosisRunContext,
    AIDiagnosisSeverity,
    AIDiagnosisStatementType,
)
from aim_api.schemas.check_run import CheckRunRead
from aim_api.services import ai_report_narratives
from aim_api.services.ai_report_narratives import (
    DETERMINISTIC_GENERATOR,
    NARRATIVE_TEXT_MAX_LENGTH,
    AIReportIssueNarrative,
    AIReportNarrative,
    apply_narrative_to_report,
    build_anthropic_narrative_generator,
    clip_narrative_text,
    enhance_report_narrative,
)

GENERATED_AT = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)


def check_run_payload(project_id: UUID, check_run_id: UUID, user_id: UUID) -> CheckRunRead:
    return CheckRunRead.model_validate(
        {
            "id": check_run_id,
            "project_id": project_id,
            "requested_by_id": user_id,
            "status": "COMPLETED",
            "trigger_source": "manual",
            "failure_reason": None,
            "queued_at": GENERATED_AT,
            "started_at": GENERATED_AT,
            "finished_at": GENERATED_AT,
            "created_at": GENERATED_AT,
            "updated_at": GENERATED_AT,
        }
    )


def build_diagnosis_input() -> AIDiagnosisInput:
    project_id = uuid4()
    check_run_id = uuid4()
    return AIDiagnosisInput(
        run_context=AIDiagnosisRunContext(
            project_id=project_id,
            check_run_id=check_run_id,
            generated_at=GENERATED_AT,
            service_url="https://example.com",
            environment="production",
        ),
        check_run=check_run_payload(project_id, check_run_id, uuid4()),
    )


def build_report() -> AIDiagnosisReport:
    return AIDiagnosisReport(
        project_id=uuid4(),
        check_run_id=uuid4(),
        generated_at=GENERATED_AT,
        summary="Deterministic summary.",
        score=AIDiagnosisReportScore(
            overall_score=55,
            grade="D",
            deployment_risk=AIDiagnosisDeploymentRisk.RISK,
            gate_reason="Critical scenario run failed.",
            evidence_ids=["score-result"],
        ),
        top_issues=[
            AIDiagnosisReportIssue(
                id="issue-availability",
                priority=1,
                title="Service unavailable",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK,
                category="availability",
                summary="The service did not respond.",
                evidence_ids=["availability-result"],
                expected_user_impact="Deterministic impact.",
                recommended_next_action="Deterministic action.",
            ),
            AIDiagnosisReportIssue(
                id="issue-performance",
                priority=2,
                title="Performance regressed",
                statement_type=AIDiagnosisStatementType.EVIDENCE_BASED_INFERENCE,
                severity=AIDiagnosisSeverity.WARNING,
                category="web_quality",
                summary="Performance score dropped below the threshold.",
                evidence_ids=["lighthouse-result"],
                expected_user_impact="Deterministic performance impact.",
                recommended_next_action="Deterministic performance action.",
            ),
        ],
    )


class FakeNarrativeGenerator:
    def __init__(
        self,
        *,
        narrative: AIReportNarrative | None = None,
        error: Exception | None = None,
        name: str = "claude-test-model",
    ) -> None:
        self.generator_name = name
        self.narrative = narrative
        self.error = error
        self.reports_seen: list[AIDiagnosisReport] = []

    def generate(
        self,
        *,
        diagnosis_input: AIDiagnosisInput,
        report: AIDiagnosisReport,
    ) -> AIReportNarrative:
        self.reports_seen.append(report)
        if self.error is not None:
            raise self.error

        assert self.narrative is not None
        return self.narrative


def test_apply_narrative_replaces_summary_and_issue_texts() -> None:
    report = build_report()
    narrative = AIReportNarrative(
        summary="LLM summary of the run.",
        issue_narratives=[
            AIReportIssueNarrative(
                issue_id="issue-availability",
                expected_user_impact="Users cannot open the site at all.",
                recommended_next_action="Check hosting and DNS status first.",
            )
        ],
    )

    enhanced = apply_narrative_to_report(report, narrative)

    assert enhanced.summary == "LLM summary of the run."
    availability_issue = enhanced.top_issues[0]
    assert availability_issue.expected_user_impact == "Users cannot open the site at all."
    assert availability_issue.recommended_next_action == "Check hosting and DNS status first."
    performance_issue = enhanced.top_issues[1]
    assert performance_issue.expected_user_impact == "Deterministic performance impact."
    assert enhanced.score == report.score
    assert [issue.id for issue in enhanced.top_issues] == [issue.id for issue in report.top_issues]
    assert availability_issue.evidence_ids == ["availability-result"]
    assert availability_issue.severity == AIDiagnosisSeverity.RISK


def test_apply_narrative_ignores_unknown_issue_ids() -> None:
    report = build_report()
    narrative = AIReportNarrative(
        summary="LLM summary of the run.",
        issue_narratives=[
            AIReportIssueNarrative(
                issue_id="issue-invented-by-llm",
                expected_user_impact="Invented impact.",
                recommended_next_action="Invented action.",
            )
        ],
    )

    enhanced = apply_narrative_to_report(report, narrative)

    assert len(enhanced.top_issues) == 2
    assert enhanced.top_issues[0].expected_user_impact == "Deterministic impact."
    assert all(issue.id != "issue-invented-by-llm" for issue in enhanced.top_issues)


def test_apply_narrative_keeps_deterministic_text_for_blank_narrative() -> None:
    report = build_report()
    narrative = AIReportNarrative(
        summary="   ",
        issue_narratives=[
            AIReportIssueNarrative(
                issue_id="issue-availability",
                expected_user_impact="",
                recommended_next_action="   ",
            )
        ],
    )

    enhanced = apply_narrative_to_report(report, narrative)

    assert enhanced.summary == "Deterministic summary."
    assert enhanced.top_issues[0].expected_user_impact == "Deterministic impact."
    assert enhanced.top_issues[0].recommended_next_action == "Deterministic action."


def test_apply_narrative_clips_overlong_text() -> None:
    report = build_report()
    narrative = AIReportNarrative(
        summary="s" * (NARRATIVE_TEXT_MAX_LENGTH + 600),
        issue_narratives=[],
    )

    enhanced = apply_narrative_to_report(report, narrative)

    assert len(enhanced.summary) == NARRATIVE_TEXT_MAX_LENGTH


def test_clip_narrative_text_returns_none_for_whitespace() -> None:
    assert clip_narrative_text("   \n ") is None
    assert clip_narrative_text(" text ") == "text"


def test_enhance_returns_deterministic_report_without_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ai_report_narratives,
        "build_anthropic_narrative_generator",
        lambda settings=None: None,
    )
    report = build_report()

    result = enhance_report_narrative(build_diagnosis_input(), report)

    assert result.generator == DETERMINISTIC_GENERATOR
    assert result.report == report


def test_enhance_applies_llm_narrative() -> None:
    report = build_report()
    generator = FakeNarrativeGenerator(
        narrative=AIReportNarrative(
            summary="LLM summary of the run.",
            issue_narratives=[],
        )
    )

    result = enhance_report_narrative(
        build_diagnosis_input(),
        report,
        narrative_generator=generator,
    )

    assert result.generator == "claude-test-model"
    assert result.report.summary == "LLM summary of the run."
    assert generator.reports_seen == [report]


def test_enhance_falls_back_when_generator_raises() -> None:
    report = build_report()
    generator = FakeNarrativeGenerator(error=RuntimeError("LLM unavailable"))

    result = enhance_report_narrative(
        build_diagnosis_input(),
        report,
        narrative_generator=generator,
    )

    assert result.generator == DETERMINISTIC_GENERATOR
    assert result.report == report


def test_build_anthropic_narrative_generator_requires_api_key() -> None:
    settings = Settings(anthropic_api_key=None)

    assert build_anthropic_narrative_generator(settings) is None


def test_build_anthropic_narrative_generator_uses_configured_model() -> None:
    settings = Settings(
        anthropic_api_key="test-api-key",
        ai_report_model="claude-opus-4-8",
        ai_report_llm_max_tokens=4096,
    )

    generator = build_anthropic_narrative_generator(settings)

    assert generator is not None
    assert generator.generator_name == "claude-opus-4-8"
    assert generator.max_tokens == 4096
