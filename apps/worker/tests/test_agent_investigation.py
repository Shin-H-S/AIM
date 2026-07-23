from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
    SslResult,
)
from aim_api.models.scenario import (
    ConsoleError,
    ScenarioRun,
    ScenarioRunStatus,
    StepResult,
    TestScenario,
    TestStep,
)
from aim_api.models.user import User
from aim_api.services import scan_queue
from aim_worker import tasks
from aim_worker.agent import investigation as investigation_module
from aim_worker.agent.db_toolbox import DbToolbox
from aim_worker.agent.investigation import run_agent_investigation_for_check_run
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SERVICE_URL = "https://svc.example"


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


@pytest.fixture(autouse=True)
def rule_only_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """조사 서비스가 LLM 없이(규칙 전용) 돌도록 고정 — 결정적 테스트."""
    monkeypatch.setattr(investigation_module, "build_llm_policy_factory", lambda: None)


def seed_project(session: Session) -> Project:
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="svc",
        service_url=SERVICE_URL,
        response_time_threshold_ms=500,
        quality_score_threshold=80,
    )
    session.add(project)
    session.commit()
    return project


def seed_check_run(
    session: Session,
    project: Project,
    *,
    status: str = CheckRunStatus.FAILED.value,
    available: bool = True,
    availability_failure: str | None = None,
    response_time_ms: int | None = 120,
    final_url: str | None = None,
    redirect_count: int = 0,
    ssl_valid: bool | None = True,
    ssl_failure: str | None = None,
    lighthouse_performance: int | None = 95,
    overall_score: int = 59,
    deployment_risk: str = "RISK",
    gate_reason: str | None = "Expected element was not found.",
) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=status,
        trigger_source="deploy",
        deploy_ref="970cfff",
    )
    session.add(check_run)
    session.flush()
    session.add(
        AvailabilityResult(
            check_run_id=check_run.id,
            service_url=SERVICE_URL,
            final_url=final_url,
            is_available=available,
            status_code=200 if available else None,
            response_time_ms=response_time_ms,
            redirect_count=redirect_count,
            uses_https=True,
            timed_out=False,
            failure_reason=availability_failure,
        )
    )
    if ssl_valid is not None:
        session.add(
            SslResult(
                check_run_id=check_run.id,
                service_url=SERVICE_URL,
                is_applicable=True,
                is_valid=ssl_valid,
                failure_reason=ssl_failure,
            )
        )
    if lighthouse_performance is not None:
        session.add(
            LighthouseResult(
                check_run_id=check_run.id,
                service_url=SERVICE_URL,
                is_successful=True,
                performance_score=lighthouse_performance,
            )
        )
    session.add(
        ScoreResult(
            check_run_id=check_run.id,
            overall_score=overall_score,
            evaluated_weight=100,
            grade="F" if overall_score < 70 else "A",
            deployment_risk=deployment_risk,
            gate_reason=gate_reason,
            scoring_version="v1",
        )
    )
    session.commit()
    return check_run


def seed_failing_scenario(session: Session, project: Project, check_run: CheckRun) -> None:
    scenario = TestScenario(project_id=project.id, name="login")
    session.add(scenario)
    session.flush()
    session.add(
        TestStep(scenario_id=scenario.id, step_order=1, action="navigate", target=f"{SERVICE_URL}/")
    )
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=project.owner_id,
        status=ScenarioRunStatus.FAILED.value,
    )
    session.add(scenario_run)
    session.flush()
    session.add_all(
        [
            StepResult(
                scenario_run_id=scenario_run.id,
                step_order=1,
                action="navigate",
                target=f"{SERVICE_URL}/",
                status="PASSED",
            ),
            StepResult(
                scenario_run_id=scenario_run.id,
                step_order=2,
                action="fill",
                target="#email",
                status="FAILED",
                error_message='no element matches selector "#email"',
            ),
            ConsoleError(
                scenario_run_id=scenario_run.id,
                level="error",
                message="TypeError: boom",
            ),
        ]
    )
    session.commit()


def test_db_toolbox_maps_rows_to_snapshots(session: Session) -> None:
    project = seed_project(session)
    check_run = seed_check_run(
        session,
        project,
        final_url=f"{SERVICE_URL}/login",
        redirect_count=1,
    )
    seed_failing_scenario(session, project, check_run)
    session.add(
        RunComparison(
            check_run_id=check_run.id,
            baseline_check_run_id=check_run.id,
            comparison_type="previous",
            overall_score_delta=-38,
            performance_score_delta=2,
            response_time_delta_ms=-10,
            deployment_risk_changed=True,
            summary="dropped",
        )
    )
    session.commit()

    toolbox = DbToolbox(session, project=project, check_run=check_run)

    check = toolbox.get_check_run()
    assert check.overall_score == 59.0
    assert check.availability_ok is True
    assert check.response_time_threshold_ms == 500
    assert check.ssl_valid is True
    assert check.lighthouse_performance == 95
    assert check.deploy_ref == "970cfff"

    steps = toolbox.get_scenario_results()
    assert [step.status for step in steps] == ["PASSED", "FAILED"]
    assert steps[1].error == 'no element matches selector "#email"'

    artifacts = toolbox.get_artifacts()
    assert artifacts.console_errors == ("TypeError: boom",)
    assert artifacts.redirect_detected_to == f"{SERVICE_URL}/login"
    assert artifacts.relocation_hint is None  # 운영 판독기 없음 — W5 과제

    baseline = toolbox.compare_with_baseline()
    assert baseline.overall_delta == -38.0
    assert baseline.performance_delta == 2

    config = toolbox.get_project_config()
    assert config.scenario_targets == (f"{SERVICE_URL}/",)


def test_db_toolbox_recent_runs(session: Session) -> None:
    project = seed_project(session)
    for score in (97, 99):
        seed_check_run(
            session,
            project,
            status=CheckRunStatus.COMPLETED.value,
            overall_score=score,
            deployment_risk="STABLE",
            gate_reason=None,
        )
    current = seed_check_run(session, project)

    toolbox = DbToolbox(session, project=project, check_run=current)
    recents = toolbox.get_recent_runs()

    assert len(recents) == 2
    assert {summary.overall_score for summary in recents} == {97.0, 99.0}
    assert all(summary.all_scenarios_passed for summary in recents)


def test_trigger_recheck_polls_to_completion(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = seed_project(session)
    check_run = seed_check_run(session, project)
    enqueued: list[UUID] = []

    def fake_enqueue(*, check_run_id: UUID) -> str:
        enqueued.append(check_run_id)
        return str(check_run_id)

    monkeypatch.setattr(scan_queue, "enqueue_check_run", fake_enqueue)

    def complete_recheck(_seconds: float) -> None:
        recheck_id = enqueued[0]
        recheck = session.get(CheckRun, recheck_id)
        assert recheck is not None
        recheck.status = CheckRunStatus.COMPLETED.value
        session.add(
            ScoreResult(
                check_run_id=recheck_id,
                overall_score=98,
                evaluated_weight=100,
                grade="A",
                deployment_risk="STABLE",
                scoring_version="v1",
            )
        )
        session.commit()

    toolbox = DbToolbox(session, project=project, check_run=check_run, sleep=complete_recheck)
    result = toolbox.trigger_recheck()

    assert result.reproduced is False  # 재검사가 정상 → 미재현(노이즈 방향)
    assert result.overall_score == 98.0
    assert toolbox.recheck_check_run_id == enqueued[0]
    recheck = session.get(CheckRun, enqueued[0])
    assert recheck is not None
    assert recheck.trigger_source == "agent_recheck"


def test_trigger_recheck_queue_unavailable_is_conservative(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = seed_project(session)
    check_run = seed_check_run(session, project)

    def broken_enqueue(*, check_run_id: UUID) -> str:
        raise scan_queue.ScanQueueUnavailableError

    monkeypatch.setattr(scan_queue, "enqueue_check_run", broken_enqueue)

    result = DbToolbox(session, project=project, check_run=check_run).trigger_recheck()

    assert result.reproduced is True  # 재검사 불능 → 보수적으로 재현 간주(G2 안전)


def test_run_investigation_persists_trace(session: Session) -> None:
    """SSL 무효 검사(규칙 확정 경로 — 재검사 불필요)의 조사가 기록된다."""
    project = seed_project(session)
    check_run = seed_check_run(
        session,
        project,
        ssl_valid=False,
        ssl_failure="certificate expired 3 days ago",
        lighthouse_performance=None,
        available=False,
        availability_failure="Service request failed.",
        response_time_ms=None,
        overall_score=12,
    )

    investigation = run_agent_investigation_for_check_run(session, check_run_id=check_run.id)

    assert investigation is not None
    assert investigation.root_cause == "ssl_invalid"
    assert investigation.generator == "rule"
    assert investigation.trigger == "incident"
    assert investigation.recheck_used is False
    assert investigation.violations == []
    assert investigation.tool_calls[0]["tool"] == "get_check_run"
    stored = session.scalars(select(AgentInvestigation)).all()
    assert len(stored) == 1


def test_run_investigation_is_idempotent_and_cooled_down(session: Session) -> None:
    project = seed_project(session)
    first_run = seed_check_run(session, project, ssl_valid=False, available=False)
    second_run = seed_check_run(session, project, ssl_valid=False, available=False)

    first = run_agent_investigation_for_check_run(session, check_run_id=first_run.id)
    duplicate = run_agent_investigation_for_check_run(session, check_run_id=first_run.id)
    cooled = run_agent_investigation_for_check_run(session, check_run_id=second_run.id)
    manual = run_agent_investigation_for_check_run(
        session, check_run_id=second_run.id, trigger="manual"
    )

    assert first is not None
    assert duplicate is None  # 검사당 1건 멱등
    assert cooled is None  # 같은 프로젝트 쿨다운
    assert manual is not None  # 수동 트리거는 쿨다운을 무시한다


def test_investigation_creates_webhook_alert(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """webhook이 설정된 프로젝트면 조사 결과가 Discord/Slack 알림으로 남는다."""
    from aim_api.models.alert import Alert

    delivered: list[UUID] = []

    def fake_delivery(*, check_run_id: UUID) -> str:
        delivered.append(check_run_id)
        return "task"

    monkeypatch.setattr(scan_queue, "enqueue_email_alert_delivery", fake_delivery)
    project = seed_project(session)
    project.alert_webhook_url = "https://discord.com/api/webhooks/1/x"
    session.commit()
    check_run = seed_check_run(
        session,
        project,
        ssl_valid=False,
        ssl_failure="certificate expired 3 days ago",
        lighthouse_performance=None,
        available=False,
        availability_failure="Service request failed.",
        response_time_ms=None,
        overall_score=12,
    )

    investigation = run_agent_investigation_for_check_run(session, check_run_id=check_run.id)

    assert investigation is not None
    alert = session.scalars(select(Alert)).one()
    assert alert.alert_type == "AGENT_INVESTIGATION"
    assert alert.channel == "WEBHOOK"
    assert "SSL 무효" in alert.subject
    assert "조치 제안" in alert.body
    assert delivered == [check_run.id]


def test_incident_open_enqueues_investigation(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = seed_project(session)
    check_run = seed_check_run(
        session,
        project,
        available=False,
        availability_failure="connect timeout",
        response_time_ms=None,
        ssl_valid=None,
        lighthouse_performance=None,
        overall_score=8,
        gate_reason="Service is unavailable: connect timeout",
    )
    captured: list[tuple[UUID, UUID | None]] = []

    def fake_enqueue(*, check_run_id: UUID, incident_id: UUID | None = None) -> str:
        captured.append((check_run_id, incident_id))
        return "task"

    monkeypatch.setattr(scan_queue, "enqueue_agent_investigation", fake_enqueue)

    availability = session.scalars(
        select(AvailabilityResult).where(AvailabilityResult.check_run_id == check_run.id)
    ).one()
    score = session.scalars(
        select(ScoreResult).where(ScoreResult.check_run_id == check_run.id)
    ).one()
    tasks.sync_check_run_incidents(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability,
        lighthouse_result=None,
        score_result=score,
    )

    assert len(captured) == 1
    assert captured[0][0] == check_run.id
    assert captured[0][1] is not None  # 새로 열린 인시던트가 연결된다
