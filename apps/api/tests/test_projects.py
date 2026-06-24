from collections.abc import Iterator
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models import Project
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client() -> Iterator[TestClient]:
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


def project_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "AIM Website",
        "service_url": "https://example.com",
        "description": "Public production site",
        "environment": "production",
        "scan_interval_minutes": 60,
        "response_time_threshold_ms": 2_000,
        "quality_score_threshold": 80,
    }
    payload.update(overrides)
    return payload


def create_project(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/projects", json=project_payload(**overrides))
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_project(client: TestClient) -> None:
    response = client.post("/projects", json=project_payload(name="  AIM API  "))

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["name"] == "AIM API"
    assert body["service_url"] == "https://example.com/"
    assert body["description"] == "Public production site"
    assert body["environment"] == "production"
    assert body["scan_interval_minutes"] == 60
    assert body["response_time_threshold_ms"] == 2_000
    assert body["quality_score_threshold"] == 80
    assert body["created_at"]
    assert body["updated_at"]


def test_list_projects(client: TestClient) -> None:
    first_project = create_project(client, name="First")
    second_project = create_project(client, name="Second")

    response = client.get("/projects")

    assert response.status_code == 200
    body = response.json()
    assert [project["id"] for project in body] == [second_project["id"], first_project["id"]]


def test_get_project(client: TestClient) -> None:
    project = create_project(client)

    response = client.get(f"/projects/{project['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == project["id"]


def test_get_project_returns_404_for_missing_project(client: TestClient) -> None:
    response = client.get(f"/projects/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_update_project(client: TestClient) -> None:
    project = create_project(client)

    response = client.patch(
        f"/projects/{project['id']}",
        json={
            "name": "Updated AIM",
            "description": None,
            "environment": "staging",
            "quality_score_threshold": 90,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == project["id"]
    assert body["name"] == "Updated AIM"
    assert body["description"] is None
    assert body["environment"] == "staging"
    assert body["quality_score_threshold"] == 90


def test_update_project_requires_at_least_one_field(client: TestClient) -> None:
    project = create_project(client)

    response = client.patch(f"/projects/{project['id']}", json={})

    assert response.status_code == 422


def test_delete_project(client: TestClient) -> None:
    project = create_project(client)

    delete_response = client.delete(f"/projects/{project['id']}")
    get_response = client.get(f"/projects/{project['id']}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_create_project_rejects_invalid_environment(client: TestClient) -> None:
    response = client.post("/projects", json=project_payload(environment="qa"))

    assert response.status_code == 422


def test_create_project_rejects_non_http_service_url(client: TestClient) -> None:
    response = client.post("/projects", json=project_payload(service_url="file:///tmp/aim"))

    assert response.status_code == 422


def test_project_table_is_registered_in_metadata() -> None:
    assert Project.__tablename__ in Base.metadata.tables
