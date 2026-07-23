from collections import Counter

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
