from aim_worker.agent.cases import ArtifactsSnapshot, CheckRunSnapshot, EvalCase
from aim_worker.agent.dataset import generate_cases
from aim_worker.agent.evaluate import (
    RuleBaselineInvestigator,
    diff_investigators,
    evaluate,
)
from aim_worker.agent.loop import (
    AgentAction,
    AgentInvestigator,
    CallTool,
    Conclude,
    InvestigationLoop,
    Observations,
)
from aim_worker.agent.policies import RouterPolicy, RulePolicy
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import FixturesToolbox


def case_by_id(case_id: str) -> EvalCase:
    return next(case for case in generate_cases() if case.case_id == case_id)


class SpyDelegate:
    """위임 여부를 세는 시험용 정책 — 항상 스테일로 결론."""

    name = "llm:test"

    def __init__(self) -> None:
        self.consulted = False

    def decide(self, observations: Observations) -> AgentAction:
        self.consulted = True
        return Conclude(RootCause.SCENARIO_STALE, "위임 결론", "조치", confidence="low")


class FeatureReadingDelegate:
    """W3 LLM이 할 일을 결정적으로 흉내내는 시험용 위임 정책 —
    이동 흔적이면 스테일, 응답 2x면 지연 파손, 아니면 UI 파손."""

    name = "oracle"

    def decide(self, observations: Observations) -> AgentAction:
        artifacts = observations.get("get_artifacts")
        if not isinstance(artifacts, ArtifactsSnapshot):
            return CallTool("get_artifacts")
        if artifacts.relocation_hint is not None:
            return Conclude(RootCause.SCENARIO_STALE, "이동 흔적", "시나리오 갱신")
        check = observations.get("get_check_run")
        if (
            isinstance(check, CheckRunSnapshot)
            and check.response_time_ms is not None
            and check.response_time_ms > 2 * check.response_time_threshold_ms
        ):
            return Conclude(RootCause.SERVER_SLOW, "지연이 스텝 파손", "서버 점검")
        return Conclude(RootCause.UI_REGRESSION, "이동 흔적 없음", "파손 수정")


def test_definitive_cases_never_reach_delegate() -> None:
    """확정 신호 케이스는 위임 정책이 아예 소환되지 않는다 — LLM 0콜의 근거."""
    for case_id, expected in (
        ("ssl_invalid-00", RootCause.SSL_INVALID),
        ("curated-gcp-vm-stopped", RootCause.SERVICE_DOWN),
        ("measurement_noise-00", RootCause.MEASUREMENT_NOISE),  # 가용성 블립
        ("server_slow-01", RootCause.SERVER_SLOW),  # 스텝 정상 + 응답 2x
        ("frontend_regression-00", RootCause.FRONTEND_REGRESSION),
    ):
        delegate = SpyDelegate()
        case = case_by_id(case_id)
        trace = InvestigationLoop(RouterPolicy(delegate), FixturesToolbox(case.fixtures)).run()

        assert trace.root_cause == expected, case_id
        assert delegate.consulted is False, case_id
        assert trace.generator == "rule", case_id


def test_failed_step_cases_are_delegated_with_generator() -> None:
    delegate = SpyDelegate()
    case = case_by_id("curated-login-moved-stale")
    trace = InvestigationLoop(RouterPolicy(delegate), FixturesToolbox(case.fixtures)).run()

    assert delegate.consulted is True
    assert trace.root_cause == RootCause.SCENARIO_STALE
    assert trace.generator == "llm:test"
    assert trace.confidence == "low"


def test_router_delegation_rate_is_59_of_175() -> None:
    """위임(=LLM 호출) 대상은 실패 스텝 케이스 59건뿐이어야 한다 — G3 비용 근거."""
    consulted = 0

    class CountingDelegate(FeatureReadingDelegate):
        def decide(self, observations: Observations) -> AgentAction:
            nonlocal consulted
            action = super().decide(observations)
            if isinstance(action, Conclude):
                consulted += 1
            return action

    cases = generate_cases()
    evaluate(AgentInvestigator(lambda: RouterPolicy(CountingDelegate())), cases)

    assert consulted == 59


def test_router_with_rule_delegate_matches_baseline() -> None:
    """라우터+규칙 위임 ≡ 베이스라인 — 라우팅이 분류를 바꾸지 않음을 증명."""
    cases = generate_cases()

    router_report = evaluate(AgentInvestigator(lambda: RouterPolicy(RulePolicy())), cases)
    baseline_report = evaluate(RuleBaselineInvestigator(), cases)

    assert router_report.accuracy == baseline_report.accuracy
    assert router_report.misclassified_case_ids == baseline_report.misclassified_case_ids


def test_router_with_feature_reading_delegate_hits_ceiling() -> None:
    """이동 흔적·응답 배율 두 특징만 읽는 위임 정책이면 175건 만점 —
    W3 LLM의 일이 정확히 이 판단이라는 문서이자, 천장 도달 가능성의 증명."""
    cases = generate_cases()
    report = evaluate(AgentInvestigator(lambda: RouterPolicy(FeatureReadingDelegate())), cases)

    assert report.accuracy == 1.0
    assert report.dangerous_misclassified_case_ids == ()


def test_churn_report_shows_fixed_and_broken() -> None:
    cases = generate_cases()
    baseline = RuleBaselineInvestigator()
    oracle = AgentInvestigator(lambda: RouterPolicy(FeatureReadingDelegate()))

    churn = diff_investigators(baseline, oracle, cases)

    assert len(churn.fixed_case_ids) == 14  # 베이스라인의 오류 전부를 고침
    assert churn.broken_case_ids == ()  # 회귀 0 — 게이트의 핵심 조건

    reverse = diff_investigators(oracle, baseline, cases)
    assert len(reverse.broken_case_ids) == 14
    assert reverse.fixed_case_ids == ()


def test_churn_report_is_empty_against_self() -> None:
    baseline = RuleBaselineInvestigator()
    churn = diff_investigators(baseline, baseline, generate_cases())

    assert churn.fixed_case_ids == ()
    assert churn.broken_case_ids == ()
