from uuid import UUID, uuid4

import pytest
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
from aim_api.services import llm_budget, scan_queue
from aim_worker import tasks
from aim_worker.agent import investigation as investigation_module
from aim_worker.agent.db_toolbox import DbToolbox, is_bad_result
from aim_worker.agent.investigation import run_agent_investigation_for_check_run
from sqlalchemy import select
from sqlalchemy.orm import Session

SERVICE_URL = "https://svc.example"


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


def test_warning_recheck_counts_as_reproduced(session: Session) -> None:
    """도그푸딩 실측(7/24): 시나리오 없는 재검사는 가용성 -40이 전체
    점수에서 희석돼(응답 임계 6배에도 91점) 점수 하한을 통과했다 —
    위험도 WARNING이면 점수와 무관하게 재현으로 판정해야 한다."""
    project = seed_project(session)
    warning_score = ScoreResult(
        check_run_id=uuid4(),
        overall_score=91,
        evaluated_weight=100,
        grade="A",
        deployment_risk="WARNING",
        gate_reason="Response time is over twice the configured threshold.",
        scoring_version="v1",
    )

    assert is_bad_result(warning_score, project=project) is True


def test_stable_recheck_over_incident_threshold_counts_as_reproduced(
    session: Session,
) -> None:
    """도그푸딩 2차(7/24): 임계 1~2배 사이 응답은 위험도 게이트(2배)에
    안 걸려 STABLE·고득점으로 산정되지만 인시던트 개시 조건(1배)은
    여전히 참이다 — 인시던트가 열린 채 '재현 안 됨'이면 모순."""
    project = seed_project(session)  # 응답 임계 500ms
    stable_score = ScoreResult(
        check_run_id=uuid4(),
        overall_score=92,
        evaluated_weight=100,
        grade="A",
        deployment_risk="STABLE",
        scoring_version="v1",
    )

    def probe(response_time_ms: int) -> AvailabilityResult:
        return AvailabilityResult(
            check_run_id=uuid4(),
            service_url=SERVICE_URL,
            is_available=True,
            status_code=200,
            response_time_ms=response_time_ms,
            redirect_count=0,
            uses_https=True,
            timed_out=False,
        )

    assert is_bad_result(stable_score, project=project, availability=probe(700)) is True
    assert is_bad_result(stable_score, project=project, availability=probe(300)) is False


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
    assert "조치: " in alert.body
    assert "검사: 12점 F · 위험" in alert.body  # 점수 맥락이 실린다
    assert delivered == [check_run.id]


def test_manual_investigation_skips_alert(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """수동 조사는 사용자가 화면에서 보므로 Discord 알림을 만들지 않는다."""
    from aim_api.models.alert import Alert

    monkeypatch.setattr(scan_queue, "enqueue_email_alert_delivery", lambda *, check_run_id: "task")
    project = seed_project(session)
    project.alert_webhook_url = "https://discord.com/api/webhooks/1/x"
    session.commit()
    check_run = seed_check_run(
        session,
        project,
        ssl_valid=False,
        available=False,
        lighthouse_performance=None,
        response_time_ms=None,
    )

    investigation = run_agent_investigation_for_check_run(
        session, check_run_id=check_run.id, trigger="manual"
    )

    assert investigation is not None
    assert session.scalars(select(Alert)).first() is None


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


def test_trigger_recheck_runs_the_scenarios_too(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """재검사에 시나리오가 붙지 않으면 원래 검사와 다른 것을 재게 된다.

    2026-07-26 도그푸딩: 시나리오 실패로 열린 인시던트가 에이전트 자신의 재검사로
    RESOLVED 처리됐다 — 재검사에 시나리오가 없어 '깨끗한' 검사로 보였기 때문이다.
    """
    project = seed_project(session)
    check_run = seed_check_run(session, project)
    seed_failing_scenario(session, project, check_run)
    enqueued_checks: list[UUID] = []
    enqueued_scenarios: list[UUID] = []

    def fake_enqueue_check(*, check_run_id: UUID) -> str:
        enqueued_checks.append(check_run_id)
        return str(check_run_id)

    def fake_enqueue_scenario(*, scenario_run_id: UUID) -> str:
        enqueued_scenarios.append(scenario_run_id)
        return str(scenario_run_id)

    monkeypatch.setattr(scan_queue, "enqueue_check_run", fake_enqueue_check)
    monkeypatch.setattr(scan_queue, "enqueue_scenario_run", fake_enqueue_scenario)

    def settle_recheck(_seconds: float) -> None:
        recheck_id = enqueued_checks[0]
        recheck = session.get(CheckRun, recheck_id)
        assert recheck is not None
        recheck.status = CheckRunStatus.COMPLETED.value
        for scenario_run in session.scalars(
            select(ScenarioRun).where(ScenarioRun.check_run_id == recheck_id)
        ).all():
            scenario_run.status = ScenarioRunStatus.FAILED.value
        session.add(
            ScoreResult(
                check_run_id=recheck_id,
                overall_score=59,
                evaluated_weight=100,
                grade="F",
                deployment_risk="RISK",
                functional_stability_score=0,
                scoring_version="v1",
            )
        )
        session.commit()

    toolbox = DbToolbox(session, project=project, check_run=check_run, sleep=settle_recheck)
    result = toolbox.trigger_recheck()

    recheck_scenarios = session.scalars(
        select(ScenarioRun).where(ScenarioRun.check_run_id == enqueued_checks[0])
    ).all()
    assert len(recheck_scenarios) == 1  # 활성 시나리오가 재검사에도 붙었다
    assert enqueued_scenarios == [recheck_scenarios[0].id]  # 큐에도 들어갔다
    assert result.reproduced is True  # 시나리오가 다시 실패했으니 재현


def test_trigger_recheck_waits_for_scenarios_before_reading_the_score(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """검사만 종결되고 시나리오가 아직이면 점수를 읽지 않는다 — 재계산 전 값을 잡지 않도록."""
    project = seed_project(session)
    check_run = seed_check_run(session, project)
    seed_failing_scenario(session, project, check_run)
    enqueued_checks: list[UUID] = []

    def fake_enqueue_check(*, check_run_id: UUID) -> str:
        enqueued_checks.append(check_run_id)
        return str(check_run_id)

    def fake_enqueue_scenario(*, scenario_run_id: UUID) -> str:
        return str(scenario_run_id)

    monkeypatch.setattr(scan_queue, "enqueue_check_run", fake_enqueue_check)
    monkeypatch.setattr(scan_queue, "enqueue_scenario_run", fake_enqueue_scenario)
    polls = {"count": 0}

    def settle_in_two_polls(_seconds: float) -> None:
        polls["count"] += 1
        recheck_id = enqueued_checks[0]
        recheck = session.get(CheckRun, recheck_id)
        assert recheck is not None
        recheck.status = CheckRunStatus.COMPLETED.value
        if polls["count"] >= 2:
            # 두 번째 폴링에서야 시나리오가 끝나고 점수가 재계산된다.
            for scenario_run in session.scalars(
                select(ScenarioRun).where(ScenarioRun.check_run_id == recheck_id)
            ).all():
                scenario_run.status = ScenarioRunStatus.COMPLETED.value
            session.add(
                ScoreResult(
                    check_run_id=recheck_id,
                    overall_score=98,
                    evaluated_weight=100,
                    grade="A",
                    deployment_risk="STABLE",
                    functional_stability_score=100,
                    scoring_version="v1",
                )
            )
        session.commit()

    toolbox = DbToolbox(session, project=project, check_run=check_run, sleep=settle_in_two_polls)
    result = toolbox.trigger_recheck()

    assert polls["count"] >= 2  # 첫 폴링에서 성급히 결론내지 않았다
    assert result.reproduced is False
    assert result.overall_score == 98.0


def test_incident_sync_waits_for_linked_scenarios(session: Session) -> None:
    """시나리오가 아직 도는 동안 인시던트를 평가하면 '실패 없음'으로 보여 잘못 해소된다.

    2026-07-26 도그푸딩: 재검사가 종결된 순간 인시던트가 해소됐다가, 시나리오가
    끝나고 재수렴이 돌자 1초 뒤 같은 인시던트가 다시 열렸다(해소→재개 플랩).
    """
    project = seed_project(session)
    check_run = seed_check_run(session, project)
    scenario = TestScenario(project_id=project.id, name="login")
    session.add(scenario)
    session.flush()
    running = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=project.owner_id,
        status=ScenarioRunStatus.RUNNING.value,
    )
    session.add(running)
    session.commit()

    assert tasks.has_pending_linked_scenario_runs(session, check_run_id=check_run.id) is True

    running.status = ScenarioRunStatus.FAILED.value
    session.commit()

    assert tasks.has_pending_linked_scenario_runs(session, check_run_id=check_run.id) is False


def test_incident_sync_proceeds_when_no_scenarios_are_linked(session: Session) -> None:
    """시나리오가 없는 검사는 기다릴 것이 없으므로 즉시 평가한다."""
    project = seed_project(session)
    check_run = seed_check_run(session, project)

    assert tasks.has_pending_linked_scenario_runs(session, check_run_id=check_run.id) is False


def seed_failed_step_with_links(
    session: Session,
    project: Project,
    check_run: CheckRun,
    *,
    page_links: list[dict[str, str]] | None,
) -> None:
    """실패 스텝 하나만 있는 시나리오 실행 — page_links 판독을 검증하기 위한 최소 구성."""
    scenario = TestScenario(project_id=project.id, name="login")
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=project.owner_id,
        status=ScenarioRunStatus.FAILED.value,
    )
    session.add(scenario_run)
    session.flush()
    session.add(
        StepResult(
            scenario_run_id=scenario_run.id,
            step_order=2,
            action="assert_element_exists",
            target="#email",
            status="FAILED",
            error_message="Expected element was not found.",
            page_links=page_links,
        )
    )
    session.commit()


def test_relocation_reader_reports_links_left_on_the_failing_page(session: Session) -> None:
    """스테일: 폼이 이사하면 그리로 가는 진입점이 남는다 — 그 사실을 증거로 옮긴다."""
    project = seed_project(session)
    check_run = seed_check_run(session, project)
    seed_failed_step_with_links(
        session,
        project,
        check_run,
        page_links=[{"path": "/login.html", "text": "로그인하러 가기"}],
    )

    artifacts = DbToolbox(session, project=project, check_run=check_run).get_artifacts()

    assert artifacts.relocation_checked is True
    assert artifacts.relocation_hint is not None
    assert "/login.html" in artifacts.relocation_hint
    assert "#email" in artifacts.relocation_hint


def test_relocation_reader_distinguishes_empty_from_uncollected(session: Session) -> None:
    """빈 목록은 '흔적이 정말 없다'는 증거(UI 파손 쪽), None은 신호 없음이다."""
    project = seed_project(session)

    collected_none = seed_check_run(session, project)
    seed_failed_step_with_links(session, project, collected_none, page_links=[])
    empty = DbToolbox(session, project=project, check_run=collected_none).get_artifacts()

    legacy = seed_check_run(session, project)
    seed_failed_step_with_links(session, project, legacy, page_links=None)
    uncollected = DbToolbox(session, project=project, check_run=legacy).get_artifacts()

    assert (empty.relocation_checked, empty.relocation_hint) == (True, None)
    assert (uncollected.relocation_checked, uncollected.relocation_hint) == (False, None)


def test_budget_breaker_downgrades_the_agent_to_the_rule_policy(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """예산 상한에 닿아도 조사는 결론을 낸다 — 멈추는 게 아니라 강등한다.

    비용 때문에 장애 진단이 통째로 사라지는 쪽이 훨씬 나쁘다.
    """
    used_llm: list[bool] = []

    def factory_that_should_not_be_used() -> object:
        used_llm.append(True)
        raise AssertionError("LLM policy must not be built once the budget is exhausted.")

    monkeypatch.setattr(
        investigation_module, "build_llm_policy_factory", lambda: factory_that_should_not_be_used
    )
    monkeypatch.setattr(
        llm_budget,
        "get_budget_status",
        lambda _session: llm_budget.BudgetStatus(
            daily_spend_usd=10.0,
            monthly_spend_usd=10.0,
            daily_limit_usd=5.0,
            monthly_limit_usd=None,
        ),
    )

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
    assert investigation.generator == "rule"
    assert investigation.llm_calls == []
    assert used_llm == []


def test_the_agent_uses_the_llm_while_within_budget(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """상한 안에서는 강등되지 않아야 한다 — 그러지 않으면 브레이커가 항상 켜진 셈이다."""
    built: list[bool] = []

    monkeypatch.setattr(
        llm_budget,
        "get_budget_status",
        lambda _session: llm_budget.BudgetStatus(
            daily_spend_usd=1.0,
            monthly_spend_usd=1.0,
            daily_limit_usd=5.0,
            monthly_limit_usd=None,
        ),
    )

    def recording_factory(**kwargs: object) -> None:
        # 운영 배선은 screenshot_loader를 넘긴다 — 팩토리 계약의 일부다.
        assert "screenshot_loader" in kwargs
        built.append(True)
        raise RuntimeError("stop here — we only need to know the factory was consulted")

    monkeypatch.setattr(investigation_module, "build_llm_policy_factory", lambda: recording_factory)

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

    with pytest.raises(RuntimeError):
        run_agent_investigation_for_check_run(session, check_run_id=check_run.id)

    assert built == [True]
