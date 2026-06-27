from collections.abc import Iterator
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.services import projects as project_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
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


def create_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/projects", json=project_payload(), headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def scenario_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Login flow",
        "description": "Critical login page smoke test",
        "is_active": True,
        "steps": [
            {"action": "navigate", "target": "https://example.com/login"},
            {"action": "fill", "target": "[name=email]", "value": "user@example.com"},
            {"action": "click", "target": "button[type=submit]"},
            {"action": "assert_url", "value": "https://example.com/dashboard"},
        ],
    }
    payload.update(overrides)
    return payload


def create_scenario(
    client: TestClient,
    *,
    project_id: str,
    headers: dict[str, str],
    **overrides: Any,
) -> dict[str, Any]:
    response = client.post(
        f"/projects/{project_id}/scenarios",
        json=scenario_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_scenario_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/projects/{uuid4()}/scenarios", json=scenario_payload())

    assert response.status_code == 401


def test_create_scenario(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)

    response = client.post(
        f"/projects/{project['id']}/scenarios",
        json=scenario_payload(name="  Login flow  "),
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["project_id"] == project["id"]
    assert body["name"] == "Login flow"
    assert body["description"] == "Critical login page smoke test"
    assert body["is_active"] is True
    assert [step["step_order"] for step in body["steps"]] == [1, 2, 3, 4]
    assert body["steps"][0]["action"] == "navigate"
    assert body["steps"][1]["target"] == "[name=email]"
    assert body["steps"][1]["value"] == "user@example.com"
    assert body["created_at"]
    assert body["updated_at"]


@pytest.mark.parametrize(
    ("step", "expected_status"),
    [
        ({"action": "navigate"}, 422),
        ({"action": "click"}, 422),
        ({"action": "fill", "target": "#email"}, 422),
        ({"action": "wait"}, 422),
        ({"action": "assert_text_exists"}, 422),
        ({"action": "assert_url"}, 422),
        ({"action": "take_screenshot"}, 201),
    ],
)
def test_create_scenario_validates_action_requirements(
    client: TestClient,
    step: dict[str, Any],
    expected_status: int,
) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)

    response = client.post(
        f"/projects/{project['id']}/scenarios",
        json=scenario_payload(steps=[step]),
        headers=headers,
    )

    assert response.status_code == expected_status


def test_list_scenarios(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    first_scenario = create_scenario(
        client, project_id=project["id"], headers=headers, name="First"
    )
    second_scenario = create_scenario(
        client,
        project_id=project["id"],
        headers=headers,
        name="Second",
    )

    response = client.get(f"/projects/{project['id']}/scenarios", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [scenario["id"] for scenario in body] == [second_scenario["id"], first_scenario["id"]]


def test_get_scenario(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    scenario = create_scenario(client, project_id=project["id"], headers=headers)

    response = client.get(
        f"/projects/{project['id']}/scenarios/{scenario['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == scenario["id"]
    assert [step["step_order"] for step in body["steps"]] == [1, 2, 3, 4]


def test_update_scenario_replaces_steps(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    scenario = create_scenario(client, project_id=project["id"], headers=headers)

    response = client.patch(
        f"/projects/{project['id']}/scenarios/{scenario['id']}",
        json={
            "name": "Checkout smoke",
            "description": None,
            "is_active": False,
            "steps": [
                {"action": "navigate", "target": "https://example.com/cart"},
                {"action": "assert_text_exists", "value": "Cart"},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Checkout smoke"
    assert body["description"] is None
    assert body["is_active"] is False
    assert [step["step_order"] for step in body["steps"]] == [1, 2]
    assert [step["action"] for step in body["steps"]] == ["navigate", "assert_text_exists"]


def test_update_scenario_requires_at_least_one_field(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    scenario = create_scenario(client, project_id=project["id"], headers=headers)

    response = client.patch(
        f"/projects/{project['id']}/scenarios/{scenario['id']}",
        json={},
        headers=headers,
    )

    assert response.status_code == 422


def test_delete_scenario(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    scenario = create_scenario(client, project_id=project["id"], headers=headers)

    delete_response = client.delete(
        f"/projects/{project['id']}/scenarios/{scenario['id']}",
        headers=headers,
    )
    get_response = client.get(
        f"/projects/{project['id']}/scenarios/{scenario['id']}",
        headers=headers,
    )

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_other_user_cannot_manage_scenario(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, email="owner@example.com")
    other_headers = authenticated_headers(client, email="other@example.com")
    project = create_project(client, owner_headers)
    scenario = create_scenario(client, project_id=project["id"], headers=owner_headers)

    list_response = client.get(f"/projects/{project['id']}/scenarios", headers=other_headers)
    get_response = client.get(
        f"/projects/{project['id']}/scenarios/{scenario['id']}",
        headers=other_headers,
    )

    assert list_response.status_code == 404
    assert list_response.json() == {"detail": "Project not found."}
    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "Project not found."}


def test_scenario_tables_are_registered_in_metadata() -> None:
    assert "test_scenarios" in Base.metadata.tables
    assert "test_steps" in Base.metadata.tables
