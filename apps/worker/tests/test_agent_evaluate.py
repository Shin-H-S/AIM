from aim_worker.agent.cases import EvalCase, ToolFixtures
from aim_worker.agent.dataset import CASES_PER_CAUSE, generate_cases, split_cases
from aim_worker.agent.evaluate import (
    EvaluationReport,
    RuleBaselineInvestigator,
    evaluate,
    select_split,
)
from aim_worker.agent.root_causes import RootCause


class FixedInvestigator:
    def __init__(self, answer: RootCause) -> None:
        self.answer = answer

    def investigate(self, fixtures: ToolFixtures) -> RootCause:
        return self.answer


def take_cases(count: int, cause: RootCause) -> tuple[EvalCase, ...]:
    matching = [case for case in generate_cases() if case.root_cause == cause]
    return tuple(matching[:count])


def test_evaluate_computes_accuracy_and_confusion() -> None:
    cases = take_cases(3, RootCause.SERVICE_DOWN) + take_cases(2, RootCause.SSL_INVALID)
    report = evaluate(FixedInvestigator(RootCause.SERVICE_DOWN), cases)

    assert report.total == 5
    assert report.correct == 3
    assert report.accuracy == 0.6
    assert report.per_cause_accuracy["service_down"] == 1.0
    assert report.per_cause_accuracy["ssl_invalid"] == 0.0
    assert report.confusion["ssl_invalid"]["service_down"] == 2
    assert len(report.misclassified_case_ids) == 2


def test_report_serializes_to_json() -> None:
    report = evaluate(
        FixedInvestigator(RootCause.SERVICE_DOWN), take_cases(2, RootCause.SERVICE_DOWN)
    )
    assert isinstance(report, EvaluationReport)
    assert '"accuracy": 1.0' in report.to_json()


def test_report_flags_dangerous_direction() -> None:
    """파손을 정상류로 판정한 오류(거짓 안심)는 G2로 별도 집계된다."""
    cases = take_cases(2, RootCause.UI_REGRESSION) + take_cases(1, RootCause.SERVER_SLOW)
    report = evaluate(FixedInvestigator(RootCause.MEASUREMENT_NOISE), cases)

    assert len(report.misclassified_case_ids) == 3
    # ui→noise 2건만 위험 방향이다 — slow→noise는 오분류지만 파손→정상류가 아니다
    assert report.dangerous_misclassified_case_ids == (
        "ui_regression-00",
        "ui_regression-01",
    )
    assert '"dangerous_count": 2' in report.to_json()


def test_rule_baseline_has_zero_dangerous_misclassifications() -> None:
    """베이스라인의 오류는 전부 안전 방향 — G2(위험 방향 0건)는 베이스라인이
    이미 만족하는 선이고, 에이전트도 이 선을 유지해야 한다."""
    dev, test = split_cases(generate_cases())
    baseline = RuleBaselineInvestigator()

    assert evaluate(baseline, dev).dangerous_misclassified_case_ids == ()
    assert evaluate(baseline, test).dangerous_misclassified_case_ids == ()


def test_rule_baseline_nails_strong_signal_causes() -> None:
    """강한 신호 유형(다운·SSL·노이즈)은 규칙만으로 만점이어야 한다."""
    baseline = RuleBaselineInvestigator()
    for cause in (RootCause.SERVICE_DOWN, RootCause.SSL_INVALID, RootCause.MEASUREMENT_NOISE):
        report = evaluate(baseline, take_cases(CASES_PER_CAUSE, cause))
        assert report.accuracy == 1.0, cause


def test_rule_baseline_is_imperfect_overall() -> None:
    """경계 사례 설계 때문에 규칙 베이스라인은 만점을 낼 수 없어야 한다 —
    이 빈틈이 LLM 에이전트가 증명해야 할 개선 여지다."""
    dev, test = split_cases(generate_cases())
    baseline = RuleBaselineInvestigator()

    dev_report = evaluate(baseline, dev)
    test_report = evaluate(baseline, test)

    assert 0.6 <= dev_report.accuracy < 1.0
    assert 0.6 <= test_report.accuracy < 1.0


def test_select_split_sizes() -> None:
    assert len(select_split("all")) == 175
    assert len(select_split("dev")) == 91
    assert len(select_split("test")) == 84
