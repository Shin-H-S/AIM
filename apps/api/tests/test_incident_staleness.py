from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aim_api.models.alert import Incident, IncidentStatus
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import incidents as incident_service
from aim_api.services.metrics import collect_metrics, render_metrics
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def signup_and_login(client: TestClient, email: str) -> dict[str, str]:
    credentials = {"email": email, "password": "correct horse battery staple"}
    client.post("/auth/signup", json=credentials)
    token = client.post("/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_project(session: Session) -> Project:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=NOW,
        environment="production",
    )
    session.add(project)
    session.flush()
    return project


def add_check_run(session: Session, *, project: Project, age_days: float) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="scheduled",
        created_at=NOW - timedelta(days=age_days),
    )
    session.add(check_run)
    session.commit()
    return check_run


def open_incident(session: Session, *, project: Project, check_run: CheckRun) -> Incident:
    incident = Incident(
        project_id=project.id,
        opened_check_run_id=check_run.id,
        trigger_type="PERFORMANCE_SCORE_BELOW_THRESHOLD",
        severity="WARNING",
        status=IncidentStatus.OPEN.value,
        title="성능 점수 임계값 미달",
        summary="Lighthouse 성능 점수가 임계값 아래입니다.",
        started_at=NOW - timedelta(days=9),
    )
    session.add(incident)
    session.commit()
    return incident


def test_a_recently_checked_project_is_not_stale() -> None:
    assert incident_service.is_stale(NOW - timedelta(days=1), now=NOW, staleness_days=7) is False


def test_a_long_unchecked_project_is_stale() -> None:
    """검사가 멈추면 해소 판정 기회 자체가 없다 — 그 사실이 드러나야 한다."""
    assert incident_service.is_stale(NOW - timedelta(days=9), now=NOW, staleness_days=7) is True


def test_a_project_that_was_never_checked_is_stale() -> None:
    assert incident_service.is_stale(None, now=NOW, staleness_days=7) is True


def test_the_boundary_is_not_stale() -> None:
    """정확히 임계일이면 아직 오래된 것이 아니다 — 경계에서 깜빡이면 안 된다."""
    assert incident_service.is_stale(NOW - timedelta(days=7), now=NOW, staleness_days=7) is False


def test_latest_check_run_is_reported_per_project(session: Session) -> None:
    first = create_project(session)
    second = create_project(session)
    add_check_run(session, project=first, age_days=9)
    add_check_run(session, project=first, age_days=1)
    add_check_run(session, project=second, age_days=30)

    latest = incident_service.latest_check_run_at_by_project(
        session, project_ids=[first.id, second.id]
    )

    assert latest[first.id].date() == (NOW - timedelta(days=1)).date()
    assert latest[second.id].date() == (NOW - timedelta(days=30)).date()


def test_projects_without_check_runs_are_absent(session: Session) -> None:
    project = create_project(session)
    session.commit()

    assert incident_service.latest_check_run_at_by_project(session, project_ids=[project.id]) == {}


def test_no_project_ids_makes_no_query(session: Session) -> None:
    assert incident_service.latest_check_run_at_by_project(session, project_ids=[]) == {}


def test_metrics_separate_stale_incidents_from_current_ones(session: Session) -> None:
    """둘을 한 숫자로 세면 '지금 조치가 필요한가'를 그 숫자로 답할 수 없다."""
    abandoned = create_project(session)
    stale_check_run = add_check_run(session, project=abandoned, age_days=9)
    open_incident(session, project=abandoned, check_run=stale_check_run)

    watched = create_project(session)
    fresh_check_run = add_check_run(session, project=watched, age_days=0.02)
    open_incident(session, project=watched, check_run=fresh_check_run)

    rendered = render_metrics(collect_metrics(session, now=NOW))

    assert 'aim_incidents_open{freshness="stale"} 1.0' in rendered
    assert 'aim_incidents_open{freshness="current"} 1.0' in rendered


def test_metrics_report_zero_for_both_buckets_when_nothing_is_open(session: Session) -> None:
    """스크레이퍼가 라벨이 사라져 그래프가 끊기는 일이 없어야 한다."""
    rendered = render_metrics(collect_metrics(session, now=NOW))

    assert 'aim_incidents_open{freshness="stale"} 0.0' in rendered
    assert 'aim_incidents_open{freshness="current"} 0.0' in rendered


def test_resolved_incidents_are_not_counted(session: Session) -> None:
    project = create_project(session)
    check_run = add_check_run(session, project=project, age_days=9)
    incident = open_incident(session, project=project, check_run=check_run)
    incident.status = IncidentStatus.RESOLVED.value
    incident.resolved_at = NOW
    session.commit()

    rendered = render_metrics(collect_metrics(session, now=NOW))

    assert 'aim_incidents_open{freshness="stale"} 0.0' in rendered


def test_the_incident_endpoint_marks_a_stale_open_incident(
    api_client: TestClient, session: Session
) -> None:
    email = f"{uuid4()}@example.com"
    headers = signup_and_login(api_client, email)
    user = session.scalars(select(User).where(User.email == email)).one()
    project = Project(
        owner_id=user.id,
        name="Abandoned",
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
        trigger_source="scheduled",
        created_at=datetime.now(UTC) - timedelta(days=9),
    )
    session.add(check_run)
    session.flush()
    open_incident(session, project=project, check_run=check_run)

    body = api_client.get(f"/projects/{project.id}/incidents", headers=headers).json()

    assert len(body) == 1
    assert body[0]["is_stale"] is True
    assert body[0]["project_last_checked_at"] is not None


def test_the_incident_endpoint_does_not_mark_a_recently_checked_project(
    api_client: TestClient, session: Session
) -> None:
    email = f"{uuid4()}@example.com"
    headers = signup_and_login(api_client, email)
    user = session.scalars(select(User).where(User.email == email)).one()
    project = Project(
        owner_id=user.id,
        name="Watched",
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
        trigger_source="scheduled",
    )
    session.add(check_run)
    session.flush()
    open_incident(session, project=project, check_run=check_run)

    body = api_client.get(f"/projects/{project.id}/incidents", headers=headers).json()

    assert body[0]["is_stale"] is False
