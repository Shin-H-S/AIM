from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact, AvailabilityResult, LighthouseResult, SslResult
from aim_api.models.user import User
from aim_api.services import artifacts, scanner_results
from sqlalchemy import create_engine, select
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
    )
    session.add(project)
    session.flush()
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=CheckRunStatus.RUNNING.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def test_record_availability_result_updates_existing_result(session: Session) -> None:
    check_run = create_check_run(session)

    first_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=True,
        status_code=200,
        response_time_ms=100,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )
    second_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=False,
        status_code=503,
        response_time_ms=250,
        redirect_count=1,
        uses_https=True,
        timed_out=False,
        failure_reason="Service returned HTTP 503.",
    )

    assert second_result.id == first_result.id
    assert session.scalars(select(AvailabilityResult)).all() == [second_result]
    assert second_result.is_available is False
    assert second_result.status_code == 503
    assert second_result.failure_reason == "Service returned HTTP 503."


def test_record_ssl_result_updates_existing_result(session: Session) -> None:
    check_run = create_check_run(session)

    first_result = scanner_results.record_ssl_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_applicable=True,
        is_valid=True,
        expires_at=datetime(2027, 6, 26, tzinfo=UTC),
        days_until_expiration=365,
        failure_reason=None,
    )
    second_result = scanner_results.record_ssl_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_applicable=True,
        is_valid=False,
        expires_at=datetime(2025, 6, 26, tzinfo=UTC),
        days_until_expiration=-365,
        failure_reason="SSL certificate is expired.",
    )

    assert second_result.id == first_result.id
    assert session.scalars(select(SslResult)).all() == [second_result]
    assert second_result.is_valid is False
    assert second_result.days_until_expiration == -365
    assert second_result.failure_reason == "SSL certificate is expired."


def test_record_lighthouse_result_updates_existing_result(session: Session) -> None:
    check_run = create_check_run(session)
    artifact = artifacts.record_artifact(
        session,
        check_run_id=check_run.id,
        artifact_type="lighthouse_raw_json",
        storage_backend="local",
        storage_path=f"check-runs/{check_run.id}/lighthouse/raw.json",
        content_type="application/json",
        size_bytes=17,
        checksum_sha256="a" * 64,
    )

    first_result = scanner_results.record_lighthouse_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        is_successful=True,
        performance_score=90,
        accessibility_score=95,
        seo_score=88,
        best_practices_score=92,
        largest_contentful_paint_ms=1200,
        cumulative_layout_shift=0.02,
        total_blocking_time_ms=30,
        raw_json_artifact_id=artifact.id,
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
            }
        ],
    )
    assert first_result.top_audits is not None
    assert first_result.top_audits[0]["id"] == "render-blocking-resources"
    second_result = scanner_results.record_lighthouse_result(
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
        failure_reason="Lighthouse CLI failed.",
    )

    assert second_result.id == first_result.id
    assert session.scalars(select(LighthouseResult)).all() == [second_result]
    assert session.scalars(select(Artifact)).all() == [artifact]
    assert second_result.is_successful is False
    assert second_result.performance_score is None
    assert second_result.top_audits is None
    assert second_result.raw_json_artifact_id is None
    assert second_result.failure_reason == "Lighthouse CLI failed."
