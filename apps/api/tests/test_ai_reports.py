from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.ai_report import AIReport
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
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


def create_check_run(session: Session) -> CheckRun:
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
    session.refresh(check_run)
    return check_run


def report_payload(check_run: CheckRun) -> dict[str, object]:
    return {
        "schema_version": "2026-06-30.ai-diagnosis-report.v1",
        "input_schema_version": "2026-06-29.ai-diagnosis-input.v1",
        "project_id": str(check_run.project_id),
        "check_run_id": str(check_run.id),
        "summary": "This run is marked as RISK.",
        "score": {
            "overall_score": 55,
            "grade": "D",
            "deployment_risk": "RISK",
            "evidence_ids": ["score-result"],
        },
        "top_issues": [
            {
                "id": "functional-risk",
                "priority": 1,
                "evidence_ids": ["scenario-run-failed"],
            }
        ],
    }


def create_ai_report(session: Session, *, check_run: CheckRun) -> AIReport:
    ai_report = AIReport(
        check_run_id=check_run.id,
        schema_version="2026-06-30.ai-diagnosis-report.v1",
        input_schema_version="2026-06-29.ai-diagnosis-input.v1",
        summary="This run is marked as RISK.",
        overall_score=55,
        grade="D",
        deployment_risk="RISK",
        gate_reason="Critical scenario run failed.",
        report_json=report_payload(check_run),
        generated_at=datetime.now(UTC),
    )
    session.add(ai_report)
    session.commit()
    session.refresh(ai_report)
    return ai_report


def test_ai_report_model_stores_report_payload(session: Session) -> None:
    check_run = create_check_run(session)

    ai_report = create_ai_report(session, check_run=check_run)

    stored_report = session.scalar(select(AIReport).where(AIReport.check_run_id == check_run.id))
    assert stored_report is not None
    assert stored_report.id == ai_report.id
    assert stored_report.schema_version == "2026-06-30.ai-diagnosis-report.v1"
    assert stored_report.input_schema_version == "2026-06-29.ai-diagnosis-input.v1"
    assert stored_report.overall_score == 55
    assert stored_report.grade == "D"
    assert stored_report.deployment_risk == "RISK"
    assert stored_report.gate_reason == "Critical scenario run failed."
    assert stored_report.report_json["check_run_id"] == str(check_run.id)
    assert stored_report.created_at is not None
    assert stored_report.updated_at is not None


def test_ai_report_model_allows_one_report_per_check_run(session: Session) -> None:
    check_run = create_check_run(session)
    create_ai_report(session, check_run=check_run)

    duplicate_report = AIReport(
        check_run_id=check_run.id,
        schema_version="2026-06-30.ai-diagnosis-report.v1",
        input_schema_version="2026-06-29.ai-diagnosis-input.v1",
        summary="Duplicate report.",
        overall_score=60,
        grade="C",
        deployment_risk="WARNING",
        gate_reason=None,
        report_json=report_payload(check_run),
        generated_at=datetime.now(UTC),
    )
    session.add(duplicate_report)

    with pytest.raises(IntegrityError):
        session.commit()


def test_ai_report_model_rejects_invalid_score_grade_and_risk(session: Session) -> None:
    check_run = create_check_run(session)
    invalid_report = AIReport(
        check_run_id=check_run.id,
        schema_version="2026-06-30.ai-diagnosis-report.v1",
        input_schema_version="2026-06-29.ai-diagnosis-input.v1",
        summary="Invalid report.",
        overall_score=101,
        grade="Z",
        deployment_risk="UNKNOWN",
        gate_reason=None,
        report_json=report_payload(check_run),
        generated_at=datetime.now(UTC),
    )
    session.add(invalid_report)

    with pytest.raises(IntegrityError):
        session.commit()
