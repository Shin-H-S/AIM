from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from aim_api.config import get_settings
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus, TestScenario
from aim_api.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_database() -> Iterator[Session]:
        with testing_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_database

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def signup_payload(email: str) -> dict[str, str]:
    return {
        "email": email,
        "password": "correct horse battery staple",
    }


def authenticated_headers(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    signup_response = client.post("/auth/signup", json=signup_payload(email))
    assert signup_response.status_code in {201, 409}
    login_response = client.post("/auth/login", json=signup_payload(email))
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def get_testing_session() -> Iterator[Session]:
    override_database = cast(Callable[[], Iterator[Session]], app.dependency_overrides[get_db])
    dependency = override_database()
    session = next(dependency)
    try:
        yield session
    finally:
        for _ in dependency:
            pass


def get_user_by_email(session: Session, *, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def create_project(session: Session, *, user: User) -> Project:
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC),
        environment="production",
    )
    session.add(project)
    session.flush()
    return project


def create_check_run_artifact(
    session: Session,
    *,
    user: User,
    artifact_root: Path,
    payload: bytes = b'{"ok": true}',
    storage_path: str | None = None,
) -> Artifact:
    project = create_project(session, user=user)
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.flush()
    artifact_storage_path = storage_path or f"check-runs/{check_run.id}/lighthouse/raw.json"
    artifact_path = artifact_root / artifact_storage_path
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(payload)
    artifact = Artifact(
        check_run_id=check_run.id,
        artifact_type="lighthouse_raw_json",
        storage_backend="local",
        storage_path=artifact_storage_path,
        content_type="application/json",
        size_bytes=len(payload),
        checksum_sha256="a" * 64,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


def create_scenario_run_artifact(
    session: Session,
    *,
    user: User,
    artifact_root: Path,
    payload: bytes = b"fake-png",
) -> Artifact:
    project = create_project(session, user=user)
    scenario = TestScenario(
        project_id=project.id,
        name="Login flow",
        description=None,
        is_active=True,
    )
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        requested_by_id=user.id,
        status=ScenarioRunStatus.FAILED.value,
        trigger_source="manual",
    )
    session.add(scenario_run)
    session.flush()
    storage_path = f"scenario-runs/{scenario_run.id}/steps/1/failure.png"
    artifact_path = artifact_root / storage_path
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(payload)
    artifact = Artifact(
        scenario_run_id=scenario_run.id,
        artifact_type="scenario_failure_screenshot",
        storage_backend="local",
        storage_path=storage_path,
        content_type="image/png",
        size_bytes=len(payload),
        checksum_sha256="b" * 64,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


def test_download_check_run_artifact(client: TestClient, tmp_path: Path) -> None:
    headers = authenticated_headers(client)
    with get_testing_session() as session:
        user = get_user_by_email(session, email="owner@example.com")
        artifact = create_check_run_artifact(session, user=user, artifact_root=tmp_path)

    response = client.get(f"/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.content == b'{"ok": true}'
    assert response.headers["content-type"] == "application/json"
    assert "raw.json" in response.headers["content-disposition"]


def test_download_scenario_run_artifact(client: TestClient, tmp_path: Path) -> None:
    headers = authenticated_headers(client)
    with get_testing_session() as session:
        user = get_user_by_email(session, email="owner@example.com")
        artifact = create_scenario_run_artifact(session, user=user, artifact_root=tmp_path)

    response = client.get(f"/artifacts/{artifact.id}/download", headers=headers)

    assert response.status_code == 200
    assert response.content == b"fake-png"
    assert response.headers["content-type"] == "image/png"
    assert "failure.png" in response.headers["content-disposition"]


def test_download_artifact_hides_other_users_artifact(
    client: TestClient,
    tmp_path: Path,
) -> None:
    owner_headers = authenticated_headers(client, email="owner@example.com")
    _ = authenticated_headers(client, email="other@example.com")
    with get_testing_session() as session:
        other_user = get_user_by_email(session, email="other@example.com")
        artifact = create_check_run_artifact(session, user=other_user, artifact_root=tmp_path)

    response = client.get(f"/artifacts/{artifact.id}/download", headers=owner_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Artifact not found."}


def test_download_artifact_rejects_path_outside_local_root(
    client: TestClient,
    tmp_path: Path,
) -> None:
    headers = authenticated_headers(client)
    outside_file = tmp_path.parent / f"{uuid4()}.txt"
    outside_file.write_bytes(b"secret")
    try:
        with get_testing_session() as session:
            user = get_user_by_email(session, email="owner@example.com")
            artifact = create_check_run_artifact(
                session,
                user=user,
                artifact_root=tmp_path,
                payload=b"",
                storage_path=f"../{outside_file.name}",
            )

        response = client.get(f"/artifacts/{artifact.id}/download", headers=headers)

        assert response.status_code == 404
        assert response.json() == {"detail": "Artifact not found."}
    finally:
        outside_file.unlink(missing_ok=True)


def test_download_artifact_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/artifacts/{UUID(int=0)}/download")

    assert response.status_code == 401
