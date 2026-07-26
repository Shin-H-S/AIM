from aim_worker.agent.cases import ArtifactsSnapshot
from aim_worker.agent.dataset import generate_cases
from aim_worker.agent.render import render_observation
from aim_worker.agent.root_causes import RootCause


def fixtures_of(case_id: str):  # type: ignore[no-untyped-def]
    return next(case for case in generate_cases() if case.case_id == case_id).fixtures


def test_check_run_card_computes_threshold_ratio() -> None:
    """판별 계산(응답/임계 배율)은 렌더러가 미리 해서 넣는다."""
    slow = next(
        case
        for case in generate_cases()
        if case.root_cause == RootCause.SERVER_SLOW and case.case_id.endswith("-00")
    )
    card = render_observation("get_check_run", slow.fixtures.check_run)

    assert "임계 500ms의" in card
    assert "배" in card
    assert "가용성 정상" in card


def test_artifacts_card_surfaces_relocation_hint() -> None:
    fixtures = fixtures_of("curated-login-moved-stale")
    card = render_observation("get_artifacts", fixtures.artifacts)

    assert "이동 흔적: " in card
    assert "/login" in card
    assert "콘솔 깨끗" in card
    assert "정상 렌더" in card


def test_artifacts_card_states_absence_of_relocation() -> None:
    """조용한 UI 파손: '이동 흔적 없음'이 명시돼야 스테일 오판을 막는다."""
    silent_ui = fixtures_of("ui_regression-02")
    card = render_observation("get_artifacts", silent_ui.artifacts)

    assert "이동 흔적 없음" in card


def test_scenario_card_summarizes_failure() -> None:
    fixtures = fixtures_of("curated-login-moved-stale")
    card = render_observation("get_scenario_results", fixtures.scenario_results)

    assert card.startswith("3스텝 중 실패 1")
    assert "FAILED" in card
    assert "no element matches" in card


def test_recheck_and_recent_runs_cards() -> None:
    fixtures = fixtures_of("measurement_noise-00")  # 가용성 블립
    recheck_card = render_observation("trigger_recheck", fixtures.recheck)
    recents_card = render_observation("get_recent_runs", fixtures.recent_runs)

    assert "미재현" in recheck_card
    assert recents_card.startswith("최근 5회")
    assert "성능 [" in recents_card


def test_unknown_tool_falls_back_to_repr() -> None:
    card = render_observation("mystery_tool", {"raw": 1})

    assert card == "{'raw': 1}"


def test_artifacts_card_separates_unknown_relocation_from_absence() -> None:
    """미수집을 '없음'으로 적으면 판단자가 없는 증거를 근거로 삼는다.

    2026-07-26 도그푸딩에서 실제로 그 일이 났다 — 운영 판독기가 없어 항상 None이
    넘어왔는데 카드가 '이동 흔적 없음'이라고 단정했고, LLM이 그 문장을 인용해
    스테일을 UI 파손으로 확신 높게 오판했다.
    """
    checked_and_absent = ArtifactsSnapshot(relocation_hint=None, relocation_checked=True)
    not_collected = ArtifactsSnapshot(relocation_hint=None, relocation_checked=False)

    absent_card = render_observation("get_artifacts", checked_and_absent)
    unknown_card = render_observation("get_artifacts", not_collected)

    assert "이동 흔적 없음" in absent_card
    assert "확인하지 못함" in unknown_card
    # 미수집 카드가 '없음'을 주장해서는 안 된다.
    assert "이동 흔적 없음" not in unknown_card
