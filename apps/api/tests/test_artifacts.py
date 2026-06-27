from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.user import User
from aim_api.services import artifacts
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


def test_record_artifact_updates_existing_path(session: Session) -> None:
    check_run = create_check_run(session)
    storage_path = f"check-runs/{check_run.id}/lighthouse/raw.json"

    first_artifact = artifacts.record_artifact(
        session,
        check_run_id=check_run.id,
        artifact_type="lighthouse_raw_json",
        storage_backend="local",
        storage_path=storage_path,
        content_type="application/json",
        size_bytes=17,
        checksum_sha256="a" * 64,
    )
    second_artifact = artifacts.record_artifact(
        session,
        check_run_id=check_run.id,
        artifact_type="lighthouse_raw_json",
        storage_backend="local",
        storage_path=storage_path,
        content_type="application/json",
        size_bytes=20,
        checksum_sha256="b" * 64,
    )

    assert second_artifact.id == first_artifact.id
    assert session.scalars(select(Artifact)).all() == [second_artifact]
    assert second_artifact.size_bytes == 20
    assert second_artifact.checksum_sha256 == "b" * 64


def test_list_artifacts_returns_check_run_artifacts(session: Session) -> None:
    check_run = create_check_run(session)
    other_check_run = create_check_run(session)
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
    artifacts.record_artifact(
        session,
        check_run_id=other_check_run.id,
        artifact_type="lighthouse_raw_json",
        storage_backend="local",
        storage_path=f"check-runs/{other_check_run.id}/lighthouse/raw.json",
        content_type="application/json",
        size_bytes=17,
        checksum_sha256="b" * 64,
    )

    assert artifacts.list_artifacts(session, check_run_id=check_run.id) == [artifact]
