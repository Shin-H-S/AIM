from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import agent_feedback
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture()
def client(api_client: TestClient) -> TestClient:
    return api_client


def signup_and_login(client: TestClient) -> dict[str, str]:
    payload = {"email": f"{uuid4()}@example.com", "password": "correct horse battery staple"}
    client.post("/auth/signup", json=payload)
    token = client.post("/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_investigation(session: Session, *, root_cause: str = "ui_regression") -> tuple[UUID, UUID]:
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
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.flush()
    session.add(
        AgentInvestigation(
            project_id=project.id,
            check_run_id=check_run.id,
            trigger="incident",
            root_cause=root_cause,
            confidence="high",
            summary="The page lost its markup.",
            recommendation="Roll back.",
            generator="llm:claude-haiku-4-5",
            recheck_used=False,
            duration_ms=1200,
        )
    )
    session.commit()
    return user.id, check_run.id


def test_an_accurate_verdict_is_recorded(session: Session) -> None:
    user_id, check_run_id = seed_investigation(session)

    investigation = agent_feedback.record_feedback(
        session, check_run_id=check_run_id, user_id=user_id, verdict="accurate"
    )

    assert investigation.feedback_verdict == "accurate"
    assert investigation.feedback_by_id == user_id
    assert investigation.feedback_at is not None


def test_an_inaccurate_verdict_carries_the_corrected_label(session: Session) -> None:
    """틀렸다는 사실보다 '무엇이 맞았는지'가 라벨로서 값어치 있다."""
    user_id, check_run_id = seed_investigation(session, root_cause="ui_regression")

    investigation = agent_feedback.record_feedback(
        session,
        check_run_id=check_run_id,
        user_id=user_id,
        verdict="inaccurate",
        root_cause="scenario_stale",
        note="셀렉터가 이사했을 뿐 화면은 멀쩡했다.",
    )

    assert investigation.feedback_verdict == "inaccurate"
    assert investigation.feedback_root_cause == "scenario_stale"
    assert investigation.root_cause == "ui_regression"


def test_feedback_can_be_changed(session: Session) -> None:
    """사람은 마음을 바꾼다 — 다시 남기면 덮어써야 한다."""
    user_id, check_run_id = seed_investigation(session)
    agent_feedback.record_feedback(
        session, check_run_id=check_run_id, user_id=user_id, verdict="accurate"
    )

    investigation = agent_feedback.record_feedback(
        session,
        check_run_id=check_run_id,
        user_id=user_id,
        verdict="inaccurate",
        root_cause="server_slow",
    )

    assert investigation.feedback_verdict == "inaccurate"
    assert investigation.feedback_root_cause == "server_slow"


def test_feedback_can_be_cleared(session: Session) -> None:
    user_id, check_run_id = seed_investigation(session)
    agent_feedback.record_feedback(
        session,
        check_run_id=check_run_id,
        user_id=user_id,
        verdict="inaccurate",
        root_cause="server_slow",
    )

    investigation = agent_feedback.clear_feedback(session, check_run_id=check_run_id)

    assert investigation.feedback_verdict is None
    assert investigation.feedback_root_cause is None
    assert investigation.feedback_at is None


def test_an_accurate_verdict_cannot_also_correct_the_cause(session: Session) -> None:
    """맞았다면서 원인을 고치는 것은 모순이고, 그대로 쌓이면 라벨이 오염된다."""
    user_id, check_run_id = seed_investigation(session)

    with pytest.raises(agent_feedback.InvalidFeedbackError, match="cannot also correct"):
        agent_feedback.record_feedback(
            session,
            check_run_id=check_run_id,
            user_id=user_id,
            verdict="accurate",
            root_cause="server_slow",
        )


def test_an_unknown_root_cause_is_rejected(session: Session) -> None:
    user_id, check_run_id = seed_investigation(session)

    with pytest.raises(agent_feedback.InvalidFeedbackError, match="Unknown root cause"):
        agent_feedback.record_feedback(
            session,
            check_run_id=check_run_id,
            user_id=user_id,
            verdict="inaccurate",
            root_cause="the_intern_did_it",
        )


def test_an_unknown_verdict_is_rejected(session: Session) -> None:
    user_id, check_run_id = seed_investigation(session)

    with pytest.raises(agent_feedback.InvalidFeedbackError, match="Unknown verdict"):
        agent_feedback.record_feedback(
            session, check_run_id=check_run_id, user_id=user_id, verdict="meh"
        )


def test_feedback_for_a_missing_investigation_is_rejected(session: Session) -> None:
    with pytest.raises(agent_feedback.InvestigationNotFoundError):
        agent_feedback.record_feedback(
            session, check_run_id=uuid4(), user_id=uuid4(), verdict="accurate"
        )


def test_feedback_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.put(
        f"/projects/{uuid4()}/check-runs/{uuid4()}/investigation/feedback",
        json={"verdict": "accurate"},
    )

    assert response.status_code == 401


def test_another_user_cannot_rate_someone_elses_investigation(
    client: TestClient, session: Session
) -> None:
    """피드백 경로로 남의 프로젝트 존재 여부가 새면 안 된다."""
    _, check_run_id = seed_investigation(session)
    headers = signup_and_login(client)

    response = client.put(
        f"/projects/{uuid4()}/check-runs/{check_run_id}/investigation/feedback",
        json={"verdict": "accurate"},
        headers=headers,
    )

    assert response.status_code == 404


def test_an_invalid_verdict_is_rejected_by_the_endpoint(
    client: TestClient, session: Session
) -> None:
    _, check_run_id = seed_investigation(session)
    headers = signup_and_login(client)

    response = client.put(
        f"/projects/{uuid4()}/check-runs/{check_run_id}/investigation/feedback",
        json={"verdict": "sort of"},
        headers=headers,
    )

    assert response.status_code in {404, 422}
