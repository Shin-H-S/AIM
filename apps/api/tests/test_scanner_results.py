from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import AvailabilityResult, SslResult
from aim_api.models.user import User
from aim_api.services import scanner_results
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
