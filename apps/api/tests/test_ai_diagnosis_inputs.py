from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import RunComparison, ScoreResult
from aim_api.models.scenario import (
    ScenarioRun,
    ScenarioRunStatus,
    StepResultStatus,
    TestScenario,
)
from aim_api.models.user import User
from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisEvidenceKind,
    AIDiagnosisSeverity,
    AIDiagnosisStatementType,
)
from aim_api.services import (
    ai_diagnosis_inputs,
    artifacts,
    check_runs,
    scanner_results,
    scenarios,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_project_and_check_run(
    session: Session,
    *,
    status: CheckRunStatus = CheckRunStatus.FAILED,
    failure_reason: str | None = "Critical scenario run failed.",
) -> tuple[Project, CheckRun]:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC),
        environment="production",
        response_time_threshold_ms=1_000,
        quality_score_threshold=80,
    )
    session.add(project)
    session.flush()
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=status.value,
        trigger_source="manual",
        failure_reason=failure_reason,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    session.add(check_run)
    session.commit()
    session.refresh(project)
    session.refresh(check_run)
    return project, check_run


def create_linked_failed_scenario_run(
    session: Session,
    *,
    project: Project,
    check_run: CheckRun,
) -> ScenarioRun:
    scenario = TestScenario(
        project_id=project.id,
        name="Login flow",
        description="Critical login flow",
        is_active=True,
    )
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=check_run.requested_by_id,
        status=ScenarioRunStatus.FAILED.value,
        trigger_source="check_run",
        failure_reason="Expected dashboard element was not found.",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=300,
    )
    session.add(scenario_run)
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def record_score_and_comparison(session: Session, *, check_run: CheckRun) -> None:
    session.add(
        ScoreResult(
            check_run_id=check_run.id,
            availability_score=0,
            functional_stability_score=0,
            web_performance_score=80,
            accessibility_score=90,
            seo_basic_quality_score=90,
            regression_stability_score=None,
            overall_score=55,
            evaluated_weight=90,
            grade="D",
            deployment_risk="RISK",
            gate_reason="Critical scenario run failed.",
            scoring_version="2026-06-28.scenario-v1",
        )
    )
    baseline_check_run = CheckRun(
        project_id=check_run.project_id,
        requested_by_id=check_run.requested_by_id,
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="manual",
    )
    session.add(baseline_check_run)
    session.flush()
    session.add(
        RunComparison(
            check_run_id=check_run.id,
            baseline_check_run_id=baseline_check_run.id,
            comparison_type="previous_run",
            overall_score_delta=-20,
            availability_score_delta=-100,
            web_performance_score_delta=-5,
            accessibility_score_delta=0,
            seo_basic_quality_score_delta=0,
            response_time_delta_ms=1500,
            performance_score_delta=-5,
            deployment_risk_changed=True,
            summary="Overall score regressed by 20.",
        )
    )
    session.commit()


def test_build_ai_diagnosis_input_collects_deterministic_results(session: Session) -> None:
    project, check_run = create_project_and_check_run(session)
    scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url=None,
        is_available=False,
        status_code=503,
        response_time_ms=2_500,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason="HTTP 503",
    )
    scanner_results.record_ssl_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_applicable=True,
        is_valid=True,
        expires_at=datetime(2027, 6, 30, tzinfo=UTC),
        days_until_expiration=365,
        failure_reason=None,
    )
    scanner_results.record_lighthouse_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_successful=False,
        performance_score=None,
        accessibility_score=None,
        seo_score=None,
        best_practices_score=None,
        largest_contentful_paint_ms=None,
        cumulative_layout_shift=None,
        total_blocking_time_ms=None,
        raw_json_artifact_id=None,
        failure_reason="Lighthouse timed out.",
    )
    artifacts.record_artifact(
        session,
        check_run_id=check_run.id,
        artifact_type="lighthouse_raw_json",
        storage_backend="local",
        storage_path=f"check-runs/{check_run.id}/lighthouse/raw.json",
        content_type="application/json",
        size_bytes=17,
        checksum_sha256="a" * 64,
    )
    scenario_run = create_linked_failed_scenario_run(
        session,
        project=project,
        check_run=check_run,
    )
    step_result = scenarios.record_step_result(
        session,
        scenario_run_id=scenario_run.id,
        test_step_id=None,
        step_order=1,
        action="assert_element_exists",
        target="#dashboard",
        status=StepResultStatus.FAILED,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=300,
        error_message="Expected dashboard element was not found.",
    )
    console_error = scenarios.record_console_error(
        session,
        scenario_run_id=scenario_run.id,
        level="error",
        message="Client crashed",
        source_url="https://example.com/app.js",
        line_number=10,
        column_number=2,
    )
    network_failure = scenarios.record_network_failure(
        session,
        scenario_run_id=scenario_run.id,
        request_url="https://example.com/api/session",
        method="GET",
        resource_type="fetch",
        failure_text="net::ERR_FAILED",
    )
    artifacts.record_artifact(
        session,
        scenario_run_id=scenario_run.id,
        artifact_type="failure_screenshot",
        storage_backend="local",
        storage_path=f"scenario-runs/{scenario_run.id}/failure.png",
        content_type="image/png",
        size_bytes=100,
        checksum_sha256="b" * 64,
    )
    record_score_and_comparison(session, check_run=check_run)

    diagnosis_input = ai_diagnosis_inputs.build_ai_diagnosis_input(
        session,
        check_run_id=check_run.id,
    )

    assert diagnosis_input.run_context.project_id == project.id
    assert diagnosis_input.run_context.service_url == project.service_url
    assert diagnosis_input.check_run.id == check_run.id
    assert diagnosis_input.score_result is not None
    assert diagnosis_input.score_result.deployment_risk == "RISK"
    assert diagnosis_input.comparison_result is not None
    assert len(diagnosis_input.scenario_evidence) == 1
    assert diagnosis_input.scenario_evidence[0].scenario_run.id == scenario_run.id
    assert diagnosis_input.scenario_evidence[0].step_results[0].id == step_result.id
    assert diagnosis_input.scenario_evidence[0].console_errors[0].id == console_error.id
    assert diagnosis_input.scenario_evidence[0].network_failures[0].id == network_failure.id
    assert len(diagnosis_input.artifacts) == 2

    evidence_kinds = {evidence.kind for evidence in diagnosis_input.evidence_items}
    assert AIDiagnosisEvidenceKind.SCORE_RESULT in evidence_kinds
    assert AIDiagnosisEvidenceKind.STEP_RESULT in evidence_kinds
    assert AIDiagnosisEvidenceKind.CONSOLE_ERROR in evidence_kinds
    assert AIDiagnosisEvidenceKind.NETWORK_FAILURE in evidence_kinds
    assert AIDiagnosisEvidenceKind.ARTIFACT in evidence_kinds

    statement_ids = {statement.id for statement in diagnosis_input.statements}
    assert "score-result-deployment-risk" in statement_ids
    assert "availability-unavailable" in statement_ids
    assert f"scenario-run-failed-{scenario_run.id}" in statement_ids
    assert f"failed-steps-{scenario_run.id}" in statement_ids
    assert f"console-errors-{scenario_run.id}" in statement_ids
    assert f"network-failures-{scenario_run.id}" in statement_ids
    assert all(
        statement.evidence_ids
        for statement in diagnosis_input.statements
        if statement.statement_type != AIDiagnosisStatementType.UNKNOWN_CAUSE
    )


def test_build_ai_diagnosis_input_creates_minimal_no_risk_statement(session: Session) -> None:
    _, check_run = create_project_and_check_run(
        session,
        status=CheckRunStatus.COMPLETED,
        failure_reason=None,
    )

    diagnosis_input = ai_diagnosis_inputs.build_ai_diagnosis_input(
        session,
        check_run_id=check_run.id,
    )

    assert [evidence.id for evidence in diagnosis_input.evidence_items] == ["check-run-status"]
    assert len(diagnosis_input.statements) == 1
    assert diagnosis_input.statements[0].id == "no-risk-evidence"


def test_build_ai_diagnosis_input_raises_when_check_run_is_missing(session: Session) -> None:
    with pytest.raises(check_runs.CheckRunNotFoundError):
        ai_diagnosis_inputs.build_ai_diagnosis_input(
            session,
            check_run_id=uuid4(),
        )


def test_build_ai_diagnosis_input_collects_lighthouse_top_audits(session: Session) -> None:
    _, check_run = create_project_and_check_run(
        session,
        status=CheckRunStatus.COMPLETED,
        failure_reason=None,
    )
    scanner_results.record_lighthouse_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_successful=True,
        performance_score=45,
        accessibility_score=90,
        seo_score=88,
        best_practices_score=92,
        largest_contentful_paint_ms=4200,
        cumulative_layout_shift=0.2,
        total_blocking_time_ms=600,
        raw_json_artifact_id=None,
        failure_reason=None,
        top_audits=[
            {
                "id": "render-blocking-resources",
                "category": "performance",
                "title": "렌더링 차단 리소스 제거하기",
                "display_value": "잠재적 절감치: 1,860ms",
                "score": 0.4,
                "savings_ms": 1860,
                "savings_bytes": None,
            },
            {
                "id": "uses-optimized-images",
                "category": "performance",
                "title": "이미지를 효율적으로 인코딩하기",
                "display_value": None,
                "score": 0.5,
                "savings_ms": 900,
                "savings_bytes": 250_000,
            },
        ],
    )

    diagnosis_input = ai_diagnosis_inputs.build_ai_diagnosis_input(
        session,
        check_run_id=check_run.id,
    )

    evidence_by_id = {item.id: item for item in diagnosis_input.evidence_items}
    first_audit = evidence_by_id["lighthouse-audit-render-blocking-resources"]
    assert first_audit.kind == AIDiagnosisEvidenceKind.LIGHTHOUSE_RESULT
    assert first_audit.summary == (
        "Lighthouse improvement opportunity: 렌더링 차단 리소스 제거하기 (잠재적 절감치: 1,860ms)"
    )
    assert first_audit.details["savings_ms"] == 1860
    assert "lighthouse-audit-uses-optimized-images" in evidence_by_id

    statement_by_id = {statement.id: statement for statement in diagnosis_input.statements}
    opportunity = statement_by_id["lighthouse-improvement-opportunities"]
    assert opportunity.severity == AIDiagnosisSeverity.WARNING
    assert opportunity.category == "web_quality"
    assert "렌더링 차단 리소스 제거하기" in opportunity.summary
    assert opportunity.evidence_ids == [
        "lighthouse-result",
        "lighthouse-audit-render-blocking-resources",
        "lighthouse-audit-uses-optimized-images",
    ]


def test_lighthouse_opportunity_statement_skipped_when_scores_meet_threshold(
    session: Session,
) -> None:
    _, check_run = create_project_and_check_run(
        session,
        status=CheckRunStatus.COMPLETED,
        failure_reason=None,
    )
    scanner_results.record_lighthouse_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_successful=True,
        performance_score=95,
        accessibility_score=96,
        seo_score=97,
        best_practices_score=98,
        largest_contentful_paint_ms=1200,
        cumulative_layout_shift=0.01,
        total_blocking_time_ms=50,
        raw_json_artifact_id=None,
        failure_reason=None,
        top_audits=[
            {
                "id": "unused-css-rules",
                "category": "performance",
                "title": "사용하지 않는 CSS 줄이기",
                "display_value": None,
                "score": 0.85,
                "savings_ms": 40,
                "savings_bytes": None,
            }
        ],
    )

    diagnosis_input = ai_diagnosis_inputs.build_ai_diagnosis_input(
        session,
        check_run_id=check_run.id,
    )

    statement_ids = [statement.id for statement in diagnosis_input.statements]
    assert "lighthouse-improvement-opportunities" not in statement_ids
    assert "lighthouse-audit-unused-css-rules" in [
        item.id for item in diagnosis_input.evidence_items
    ]
