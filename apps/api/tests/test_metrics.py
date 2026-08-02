from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aim_api.config import get_settings
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.ai_report import AIReport
from aim_api.models.alert import Incident, IncidentStatus
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.user import User
from aim_api.services.metrics import Metric, collect_metrics, render_metrics
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

METRICS_TOKEN = "scrape-me-please"


@pytest.fixture()
def metrics_client(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("METRICS_TOKEN", METRICS_TOKEN)
    get_settings.cache_clear()
    yield api_client
    get_settings.cache_clear()


@pytest.fixture()
def disabled_metrics_client(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    get_settings.cache_clear()
    yield api_client
    get_settings.cache_clear()


def authorized() -> dict[str, str]:
    return {"Authorization": f"Bearer {METRICS_TOKEN}"}


def create_project(session: Session) -> Project:
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
    return project


def add_check_run(
    session: Session,
    *,
    project: Project,
    status: str = CheckRunStatus.COMPLETED.value,
    duration_seconds: float | None = None,
) -> CheckRun:
    started_at = datetime.now(UTC)
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=status,
        trigger_source="manual",
        started_at=started_at if duration_seconds is not None else None,
        finished_at=(
            started_at + timedelta(seconds=duration_seconds)
            if duration_seconds is not None
            else None
        ),
    )
    session.add(check_run)
    session.commit()
    return check_run


def test_render_uses_the_prometheus_exposition_format() -> None:
    rendered = render_metrics(
        [
            Metric(
                name="aim_thing_total",
                help_text="A thing.",
                metric_type="gauge",
                samples=[({"status": "COMPLETED"}, 3.0), ({}, 7.0)],
            )
        ]
    )

    assert "# HELP aim_thing_total A thing." in rendered
    assert "# TYPE aim_thing_total gauge" in rendered
    assert 'aim_thing_total{status="COMPLETED"} 3.0' in rendered
    assert "aim_thing_total 7.0" in rendered
    assert rendered.endswith("\n")


def test_render_escapes_label_values() -> None:
    rendered = render_metrics(
        [
            Metric(
                name="aim_thing_total",
                help_text="A thing.",
                metric_type="gauge",
                samples=[({"model": 'we"ird\\'}, 1.0)],
            )
        ]
    )

    assert 'model="we\\"ird\\\\"' in rendered


def test_check_runs_are_counted_by_status(session: Session) -> None:
    project = create_project(session)
    add_check_run(session, project=project, status=CheckRunStatus.COMPLETED.value)
    add_check_run(session, project=project, status=CheckRunStatus.COMPLETED.value)
    add_check_run(session, project=project, status=CheckRunStatus.FAILED.value)

    rendered = render_metrics(collect_metrics(session))

    assert 'aim_check_runs_total{status="COMPLETED"} 2.0' in rendered
    assert 'aim_check_runs_total{status="FAILED"} 1.0' in rendered


def test_average_duration_covers_only_finished_runs(session: Session) -> None:
    project = create_project(session)
    add_check_run(session, project=project, duration_seconds=10.0)
    add_check_run(session, project=project, duration_seconds=20.0)
    add_check_run(session, project=project, status=CheckRunStatus.RUNNING.value)

    rendered = render_metrics(collect_metrics(session))

    assert "aim_check_run_duration_seconds_avg 15.0" in rendered


def test_average_duration_is_zero_when_nothing_finished(session: Session) -> None:
    """스크레이퍼가 빈 값을 받고 깨지지 않아야 한다."""
    rendered = render_metrics(collect_metrics(session))

    assert "aim_check_run_duration_seconds_avg 0.0" in rendered


def test_open_incidents_are_counted(session: Session) -> None:
    project = create_project(session)
    check_run = add_check_run(session, project=project)
    for incident_status in (IncidentStatus.OPEN.value, IncidentStatus.OPEN.value):
        session.add(
            Incident(
                project_id=project.id,
                opened_check_run_id=check_run.id,
                trigger_type="SERVICE_CONNECTION_FAILURE",
                severity="RISK",
                status=incident_status,
                title="Service is down",
                summary="Connection refused",
                started_at=datetime.now(UTC),
            )
        )
    session.commit()

    rendered = render_metrics(collect_metrics(session))

    # freshness × project로 나뉜다 — 운영자가 자기 프로젝트만 골라 경보를
    # 걸 수 있어야 외부 사용자 인시던트가 경보를 점유하지 않는다(7/31 실측).
    assert 'aim_incidents_open{freshness="current",project="AIM Website"} 2.0' in rendered


def test_no_open_incidents_still_emits_a_zero_sample(session: Session) -> None:
    """인시던트가 없어도 시계열이 끊기면 스크레이퍼가 '없음'과 '고장'을 구분 못 한다."""
    rendered = render_metrics(collect_metrics(session))

    assert 'aim_incidents_open{freshness="current",project=""} 0.0' in rendered


def test_ai_reports_are_counted_by_generator(session: Session) -> None:
    """LLM 서술과 결정론 폴백의 비율은 운영에서 보고 싶은 값이다."""
    project = create_project(session)
    for generator in ("llm", "deterministic", "deterministic"):
        check_run = add_check_run(session, project=project)
        session.add(
            AIReport(
                check_run_id=check_run.id,
                schema_version="1.0",
                input_schema_version="1.0",
                summary="Looks fine.",
                overall_score=90,
                grade="A",
                deployment_risk="STABLE",
                generator=generator,
                report_json={},
                generated_at=datetime.now(UTC),
            )
        )
    session.commit()

    rendered = render_metrics(collect_metrics(session))

    assert 'aim_ai_reports_total{generator="deterministic"} 2.0' in rendered
    assert 'aim_ai_reports_total{generator="llm"} 1.0' in rendered


def test_agent_tokens_are_summed_per_model(session: Session) -> None:
    project = create_project(session)
    check_run = add_check_run(session, project=project)
    session.add(
        AgentInvestigation(
            project_id=project.id,
            check_run_id=check_run.id,
            trigger="incident",
            root_cause="ui_regression",
            confidence="high",
            summary="The page lost its markup.",
            recommendation="Roll back.",
            generator="llm",
            recheck_used=False,
            duration_ms=1200,
            llm_calls=[
                {"model": "claude-haiku-4-5", "input_tokens": 100, "output_tokens": 20},
                {"model": "claude-haiku-4-5", "input_tokens": 50, "output_tokens": 10},
            ],
        )
    )
    session.commit()

    rendered = render_metrics(collect_metrics(session))

    assert 'aim_agent_llm_tokens_total{kind="input",model="claude-haiku-4-5"} 150.0' in rendered
    assert 'aim_agent_llm_tokens_total{kind="output",model="claude-haiku-4-5"} 30.0' in rendered


def test_artifact_bytes_are_reported(session: Session) -> None:
    """보존 정책이 도는지 감시하는 값이다."""
    project = create_project(session)
    check_run = add_check_run(session, project=project)
    for size in (100, 250):
        session.add(
            Artifact(
                check_run_id=check_run.id,
                artifact_type="lighthouse_json",
                storage_backend="local",
                storage_path=f"check-runs/{check_run.id}/{uuid4()}.json",
                content_type="application/json",
                size_bytes=size,
                checksum_sha256="0" * 64,
            )
        )
    session.commit()

    rendered = render_metrics(collect_metrics(session))

    assert "aim_artifacts_bytes 350.0" in rendered
    assert "aim_artifacts_total 2.0" in rendered


def test_metrics_require_the_scrape_token(metrics_client: TestClient) -> None:
    response = metrics_client.get("/metrics")

    assert response.status_code == 404


def test_a_wrong_token_is_indistinguishable_from_a_disabled_endpoint(
    metrics_client: TestClient,
) -> None:
    response = metrics_client.get("/metrics", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 404


def test_metrics_are_served_with_the_scrape_token(metrics_client: TestClient) -> None:
    response = metrics_client.get("/metrics", headers=authorized())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "aim_check_runs_total" in response.text


def test_metrics_are_closed_when_no_token_is_configured(
    disabled_metrics_client: TestClient,
) -> None:
    """설정하지 않은 배포에서 운영 현황이 열려 있으면 안 된다."""
    response = disabled_metrics_client.get("/metrics", headers=authorized())

    assert response.status_code == 404


def test_agent_feedback_is_counted_by_verdict(session: Session) -> None:
    """피드백이 쌓이는지 볼 수단이 없으면 채널이 죽어도 모른다."""
    project = create_project(session)
    for verdict in ("accurate", "accurate", "inaccurate", None):
        check_run = add_check_run(session, project=project)
        session.add(
            AgentInvestigation(
                project_id=project.id,
                check_run_id=check_run.id,
                trigger="incident",
                root_cause="ui_regression",
                confidence="high",
                summary="s",
                recommendation="r",
                generator="rule",
                recheck_used=False,
                duration_ms=100,
                feedback_verdict=verdict,
            )
        )
    session.commit()

    rendered = render_metrics(collect_metrics(session))

    assert 'aim_agent_feedback_total{verdict="accurate"} 2.0' in rendered
    assert 'aim_agent_feedback_total{verdict="inaccurate"} 1.0' in rendered


def test_agent_feedback_emits_both_buckets_when_empty(session: Session) -> None:
    """라벨이 사라지면 스크레이퍼의 시계열이 끊긴다."""
    rendered = render_metrics(collect_metrics(session))

    assert 'aim_agent_feedback_total{verdict="accurate"} 0.0' in rendered
    assert 'aim_agent_feedback_total{verdict="inaccurate"} 0.0' in rendered


def get_metric(metrics: list[Metric], name: str) -> Metric:
    return next(metric for metric in metrics if metric.name == name)


def test_overdue_counts_projects_the_scheduler_has_abandoned(session: Session) -> None:
    """마지막 검사가 주기의 2배를 넘긴 옵트인 프로젝트가 심장박동 경보의 대상이다."""
    project = create_project(session)
    project.scheduled_scans_enabled = True
    project.scan_interval_minutes = 60
    session.commit()
    check_run = add_check_run(session, project=project)
    check_run.created_at = datetime.now(UTC) - timedelta(minutes=121)
    session.commit()

    metric = get_metric(collect_metrics(session), "aim_scheduled_scans_overdue")

    assert metric.samples == [({}, 1.0)]


def test_a_recent_scan_keeps_the_heartbeat_quiet(session: Session) -> None:
    project = create_project(session)
    project.scheduled_scans_enabled = True
    project.scan_interval_minutes = 60
    session.commit()
    add_check_run(session, project=project)

    metric = get_metric(collect_metrics(session), "aim_scheduled_scans_overdue")

    assert metric.samples == [({}, 0.0)]


def test_opted_out_and_unverified_projects_are_not_counted(session: Session) -> None:
    """스케줄러가 애초에 안 볼 프로젝트는 밀린 것도 아니다 — 오탐 방지."""
    opted_out = create_project(session)
    opted_out.scheduled_scans_enabled = False
    unverified = create_project(session)
    unverified.scheduled_scans_enabled = True
    unverified.verified_at = None
    session.commit()
    for project in (opted_out, unverified):
        run = add_check_run(session, project=project)
        run.created_at = datetime.now(UTC) - timedelta(days=30)
    session.commit()

    metric = get_metric(collect_metrics(session), "aim_scheduled_scans_overdue")

    assert metric.samples == [({}, 0.0)]


def test_a_never_scanned_project_is_graded_from_its_last_config_change(
    session: Session,
) -> None:
    """검사 이력이 없으면 설정 변경 시각 기준 — 방금 켠 프로젝트는 오탐하지 않는다."""
    project = create_project(session)
    project.scheduled_scans_enabled = True
    project.scan_interval_minutes = 60
    session.commit()

    fresh = get_metric(collect_metrics(session), "aim_scheduled_scans_overdue")
    assert fresh.samples == [({}, 0.0)]

    project.updated_at = datetime.now(UTC) - timedelta(minutes=121)
    session.commit()
    stale = get_metric(collect_metrics(session), "aim_scheduled_scans_overdue")
    assert stale.samples == [({}, 1.0)]
