from collections import Counter

from aim_worker.agent.cases import EvalCase
from aim_worker.agent.dataset import CASES_PER_CAUSE, generate_cases, split_cases
from aim_worker.agent.root_causes import RootCause


def test_generates_balanced_dataset() -> None:
    cases = generate_cases()

    assert len(cases) == CASES_PER_CAUSE * len(RootCause) == 105
    counts = Counter(case.root_cause for case in cases)
    assert all(counts[cause] == CASES_PER_CAUSE for cause in RootCause)


def test_case_ids_are_unique() -> None:
    cases = generate_cases()
    ids = [case.case_id for case in cases]
    assert len(ids) == len(set(ids))


def test_generation_is_deterministic() -> None:
    assert generate_cases() == generate_cases()


def test_curated_incidents_are_included() -> None:
    cases = {case.case_id: case for case in generate_cases()}

    assert cases["curated-gcp-vm-stopped"].root_cause == RootCause.SERVICE_DOWN
    assert cases["curated-e2-downsize-perf"].root_cause == RootCause.FRONTEND_REGRESSION
    assert cases["curated-login-moved-stale"].root_cause == RootCause.SCENARIO_STALE
    assert all(case.curated for case in cases.values() if case.case_id.startswith("curated-"))


def test_split_keeps_cause_balance_and_covers_everything() -> None:
    cases = generate_cases()
    dev, test = split_cases(cases)

    assert len(dev) + len(test) == len(cases)
    assert not {case.case_id for case in dev} & {case.case_id for case in test}
    dev_counts = Counter(case.root_cause for case in dev)
    test_counts = Counter(case.root_cause for case in test)
    for cause in RootCause:
        # 15건을 교차 배분하면 8/7 — 유형 균형이 유지된다.
        assert dev_counts[cause] == 8
        assert test_counts[cause] == 7


def test_labels_carry_discriminating_evidence() -> None:
    """정답 라벨이 fixtures의 증거와 모순되지 않는지 최소 불변식을 확인한다."""
    for case in generate_cases():
        fixtures = case.fixtures
        if case.root_cause == RootCause.SERVICE_DOWN:
            assert not fixtures.check_run.availability_ok
        if case.root_cause == RootCause.SSL_INVALID:
            assert fixtures.check_run.ssl_valid is False
        if case.root_cause == RootCause.MEASUREMENT_NOISE:
            assert not fixtures.recheck.reproduced
        else:
            assert fixtures.recheck.reproduced
        if case.root_cause == RootCause.SCENARIO_STALE:
            assert fixtures.artifacts.failing_page_rendered_ok is True
            assert not fixtures.artifacts.console_errors
            assert fixtures.artifacts.relocation_hint is not None
        if case.root_cause == RootCause.UI_REGRESSION:
            assert fixtures.artifacts.relocation_hint is None


def _failed_error_kind(case: EvalCase) -> str | None:
    """실패 스텝 에러의 의미 부류 — 문자열 원문 대신 조사자가 읽는 의미만 본다."""
    error = next(
        (step.error for step in case.fixtures.scenario_results if step.status == "FAILED"), None
    )
    if error is None:
        return None
    if "no element matches" in error:
        return "selector_not_found"
    if "not clickable" in error:
        return "not_clickable"
    if "expected text" in error:
        return "text_not_found"
    if "timeout waiting" in error:
        return "wait_timeout"
    return "network_level"


def _genuine_signature(case: EvalCase) -> tuple[object, ...]:
    """정당한 판별 증거만 모은 서명.

    스텝 개수·navigate URL 문자열·케이스 제목 같은 생성 부산물은 일부러
    제외한다 — 그런 것으로 라벨을 맞히는 조사기는 과적합이기 때문이다.
    """
    fixtures = case.fixtures
    check = fixtures.check_run
    artifacts = fixtures.artifacts
    return (
        check.availability_ok,
        check.ssl_valid,
        fixtures.recheck.reproduced,
        check.response_time_ms is not None
        and check.response_time_ms > 2 * check.response_time_threshold_ms,
        _failed_error_kind(case),
        artifacts.failing_page_rendered_ok,
        bool(artifacts.console_errors),
        bool(artifacts.network_failures),
        artifacts.redirect_detected_to is not None,
        artifacts.relocation_hint is not None,
        fixtures.baseline.performance_delta is not None
        and fixtures.baseline.performance_delta <= -10,
    )


def test_labels_are_separable_on_genuine_evidence() -> None:
    """같은 정당-증거 서명에 서로 다른 라벨이 섞이면 그 케이스들은 어떤
    조사기도 원리상 판별할 수 없고, 채점이 라벨 노이즈를 측정하게 된다.
    v1 감사(2026-07-20)에서 이 충돌 6건을 찾아 relocation_hint로 해소했다 —
    이 테스트는 그 분리성이 다시 깨지지 않도록 고정한다."""
    labels_by_signature: dict[tuple[object, ...], set[RootCause]] = {}
    for case in generate_cases():
        labels_by_signature.setdefault(_genuine_signature(case), set()).add(case.root_cause)

    colliding = {
        signature: labels for signature, labels in labels_by_signature.items() if len(labels) > 1
    }
    assert not colliding
