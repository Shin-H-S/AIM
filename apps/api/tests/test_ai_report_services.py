from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.ai_report import AIReport
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import ScoreResult
from aim_api.models.user import User
from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisDeploymentRisk,
    AIDiagnosisReport,
    AIDiagnosisReportIssue,
    AIDiagnosisReportScore,
    AIDiagnosisSeverity,
    AIDiagnosisStatementType,
)
from aim_api.services import ai_reports
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

ReportGrade = Literal["A", "B", "C", "D", "F"]


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


def create_project_and_check_run(session: Session) -> tuple[Project, CheckRun]:
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
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="manual",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    session.add(check_run)
    session.commit()
    session.refresh(project)
    session.refresh(check_run)
    return project, check_run


def report_payload(
    *,
    project: Project,
    check_run: CheckRun,
    generated_at: datetime,
    deployment_risk: AIDiagnosisDeploymentRisk = AIDiagnosisDeploymentRisk.RISK,
    grade: ReportGrade = "D",
    overall_score: int = 55,
) -> AIDiagnosisReport:
    top_issues: list[AIDiagnosisReportIssue] = []
    if deployment_risk != AIDiagnosisDeploymentRisk.STABLE:
        top_issues = [
            AIDiagnosisReportIssue(
                id="deployment-risk-score-result",
                priority=1,
                title="Deployment risk from deterministic score",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK
                if deployment_risk == AIDiagnosisDeploymentRisk.RISK
                else AIDiagnosisSeverity.WARNING,
                category="deployment_risk",
                summary="Deterministic scoring marked this run as risky.",
                evidence_ids=["score-result"],
                expected_user_impact="The deployment may be risky.",
                recommended_next_action="Review the deterministic gate reason first.",
            )
        ]

    return AIDiagnosisReport(
        project_id=project.id,
        check_run_id=check_run.id,
        generated_at=generated_at,
        summary=f"This run is marked as {deployment_risk.value}.",
        score=AIDiagnosisReportScore(
            overall_score=overall_score,
            grade=grade,
            deployment_risk=deployment_risk,
            gate_reason="Critical scenario run failed."
            if deployment_risk == AIDiagnosisDeploymentRisk.RISK
            else None,
            evidence_ids=["score-result"],
        ),
        top_issues=top_issues,
    )


def record_score_result(
    session: Session,
    *,
    check_run: CheckRun,
    deployment_risk: str = "RISK",
    grade: str = "D",
    overall_score: int = 55,
) -> ScoreResult:
    score_result = ScoreResult(
        check_run_id=check_run.id,
        availability_score=100,
        functional_stability_score=0,
        web_performance_score=80,
        accessibility_score=90,
        seo_basic_quality_score=90,
        regression_stability_score=None,
        overall_score=overall_score,
        evaluated_weight=90,
        grade=grade,
        deployment_risk=deployment_risk,
        gate_reason="Critical scenario run failed." if deployment_risk == "RISK" else None,
        scoring_version="2026-06-28.scenario-v1",
    )
    session.add(score_result)
    session.commit()
    session.refresh(score_result)
    return score_result


def test_record_ai_report_creates_report(session: Session) -> None:
    project, check_run = create_project_and_check_run(session)
    report = report_payload(
        project=project,
        check_run=check_run,
        generated_at=datetime(2026, 6, 30, 1, tzinfo=UTC),
    )

    ai_report = ai_reports.record_ai_report(session, report=report)

    stored_report = ai_reports.get_ai_report(session, check_run_id=check_run.id)
    assert stored_report.id == ai_report.id
    assert stored_report.check_run_id == check_run.id
    assert stored_report.summary == report.summary
    assert stored_report.overall_score == 55
    assert stored_report.grade == "D"
    assert stored_report.deployment_risk == "RISK"
    assert stored_report.gate_reason == "Critical scenario run failed."
    assert stored_report.report_json["check_run_id"] == str(check_run.id)


def test_record_ai_report_updates_existing_report(session: Session) -> None:
    project, check_run = create_project_and_check_run(session)
    first_report = report_payload(
        project=project,
        check_run=check_run,
        generated_at=datetime(2026, 6, 30, 1, tzinfo=UTC),
    )
    first_ai_report = ai_reports.record_ai_report(session, report=first_report)
    second_report = report_payload(
        project=project,
        check_run=check_run,
        generated_at=datetime(2026, 6, 30, 2, tzinfo=UTC),
        deployment_risk=AIDiagnosisDeploymentRisk.WARNING,
        grade="C",
        overall_score=72,
    )

    second_ai_report = ai_reports.record_ai_report(session, report=second_report)

    assert second_ai_report.id == first_ai_report.id
    assert second_ai_report.summary == "This run is marked as WARNING."
    assert second_ai_report.overall_score == 72
    assert second_ai_report.grade == "C"
    assert second_ai_report.deployment_risk == "WARNING"
    assert second_ai_report.gate_reason is None
    assert session.scalars(select(AIReport)).all() == [second_ai_report]


def test_generate_and_record_ai_report_uses_stored_check_run_results(session: Session) -> None:
    _, check_run = create_project_and_check_run(session)
    record_score_result(session, check_run=check_run)

    ai_report = ai_reports.generate_and_record_ai_report(
        session,
        check_run_id=check_run.id,
        generated_at=datetime(2026, 6, 30, 3, tzinfo=UTC),
    )
    report_score = cast(dict[str, object], ai_report.report_json["score"])

    assert ai_report.check_run_id == check_run.id
    assert ai_report.overall_score == 55
    assert ai_report.deployment_risk == "RISK"
    assert report_score["deployment_risk"] == "RISK"
    assert ai_report.report_json["top_issues"]
    assert ai_report.report_json["generation_warnings"] == [
        "No run comparison was available, so changed areas are empty."
    ]


def test_get_ai_report_raises_when_report_is_missing(session: Session) -> None:
    with pytest.raises(ai_reports.AIReportNotFoundError):
        ai_reports.get_ai_report(session, check_run_id=uuid4())
