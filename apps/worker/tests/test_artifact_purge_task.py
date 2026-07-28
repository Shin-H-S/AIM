from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from aim_api.config import get_settings
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.user import User
from aim_worker import tasks
from aim_worker.artifacts import store_binary_artifact
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("ARTIFACT_RETENTION_DAYS", "14")
    monkeypatch.setenv("ARTIFACT_INCIDENT_RETENTION_DAYS", "90")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture()
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(tasks, "SessionLocal", testing_session_local)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_check_run(session: Session, *, status: str = CheckRunStatus.COMPLETED.value) -> CheckRun:
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
        status=status,
        trigger_source="manual",
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def store_artifact(
    session: Session,
    *,
    check_run_id: UUID,
    age_days: int,
    payload: bytes = b"{}",
) -> Artifact:
    storage_path = f"check-runs/{check_run_id}/{uuid4()}.json"
    stored = store_binary_artifact(
        artifact_type="lighthouse_raw_json",
        storage_path=storage_path,
        content_type="application/json",
        payload=payload,
    )
    artifact = Artifact(
        check_run_id=check_run_id,
        artifact_type=stored.artifact_type,
        storage_backend=stored.storage_backend,
        storage_path=stored.storage_path,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,
        created_at=datetime.now(UTC) - timedelta(days=age_days),
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


def test_purge_removes_expired_files_and_records(session: Session, artifact_root: Path) -> None:
    check_run = create_check_run(session)
    expired = store_artifact(session, check_run_id=check_run.id, age_days=30)

    result = tasks.purge_expired_artifacts()

    assert result["deleted_record_count"] == 1
    assert result["deleted_file_count"] == 1
    assert result["missing_file_count"] == 0
    assert not (artifact_root / expired.storage_path).exists()
    assert session.scalar(select(Artifact).where(Artifact.id == expired.id)) is None


def test_purge_keeps_artifacts_inside_the_retention_window(
    session: Session, artifact_root: Path
) -> None:
    check_run = create_check_run(session)
    kept = store_artifact(session, check_run_id=check_run.id, age_days=3)

    result = tasks.purge_expired_artifacts()

    assert result["deleted_record_count"] == 0
    assert (artifact_root / kept.storage_path).exists()
    assert session.scalar(select(Artifact).where(Artifact.id == kept.id)) is not None


def test_purge_removes_the_record_when_the_file_is_already_gone(
    session: Session, artifact_root: Path
) -> None:
    """파일만 먼저 사라진 상태에서도 레코드는 정리돼야 한다 — 재실행이 마저 끝낸다."""
    check_run = create_check_run(session)
    expired = store_artifact(session, check_run_id=check_run.id, age_days=30)
    (artifact_root / expired.storage_path).unlink()

    result = tasks.purge_expired_artifacts()

    assert result["deleted_record_count"] == 1
    assert result["deleted_file_count"] == 0
    assert result["missing_file_count"] == 1
    assert session.scalar(select(Artifact).where(Artifact.id == expired.id)) is None


def test_purge_respects_the_batch_size(
    session: Session, artifact_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARTIFACT_PURGE_BATCH_SIZE", "1")
    get_settings.cache_clear()
    check_run = create_check_run(session)
    store_artifact(session, check_run_id=check_run.id, age_days=30)
    store_artifact(session, check_run_id=check_run.id, age_days=31)

    result = tasks.purge_expired_artifacts()

    assert result["deleted_record_count"] == 1
    assert session.scalars(select(Artifact)).all() != []


def test_purge_is_a_no_op_when_nothing_expired(session: Session, artifact_root: Path) -> None:
    result = tasks.purge_expired_artifacts()

    assert result == {
        "deleted_record_count": 0,
        "deleted_file_count": 0,
        "missing_file_count": 0,
    }
