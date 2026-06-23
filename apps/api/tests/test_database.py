from collections.abc import Iterator
from unittest.mock import MagicMock

from aim_api import database
from aim_api.database import get_db
from aim_api.main import app
from fastapi.testclient import TestClient
from pytest import MonkeyPatch, raises
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

client = TestClient(app)


def test_database_dependency_closes_session(monkeypatch: MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_factory = MagicMock(return_value=session_context)
    monkeypatch.setattr(database, "SessionLocal", session_factory)

    dependency = get_db()

    assert next(dependency) is session
    with raises(StopIteration):
        next(dependency)

    session_context.__exit__.assert_called_once()


def test_database_health_check() -> None:
    session = MagicMock(spec=Session)

    def override_database() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_database

    try:
        response = client.get("/health/database")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "available",
    }
    session.execute.assert_called_once()


def test_database_health_check_does_not_expose_connection_details() -> None:
    session = MagicMock(spec=Session)
    session.execute.side_effect = OperationalError(
        statement="SELECT 1",
        params={},
        orig=RuntimeError("postgresql://user:password@internal-host/aim"),
    )

    def override_database() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_database

    try:
        response = client.get("/health/database")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}
    assert "internal-host" not in response.text
