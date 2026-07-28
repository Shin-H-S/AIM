from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aim_api.config import Settings
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import llm_budget
from sqlalchemy.orm import Session

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def budget_settings(
    *, daily: float | None = None, monthly: float | None = None, rates_json: str | None = None
) -> Settings:
    return Settings(
        _env_file=None,
        aim_agent_daily_budget_usd=daily,
        aim_agent_monthly_budget_usd=monthly,
        aim_agent_model_rates_json=rates_json,
    )


def add_investigation(
    session: Session,
    *,
    llm_calls: list[dict[str, object]],
    age_days: float = 0.0,
) -> None:
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
            root_cause="ui_regression",
            confidence="high",
            summary="s",
            recommendation="r",
            generator="llm:claude-haiku-4-5",
            recheck_used=False,
            duration_ms=1000,
            llm_calls=llm_calls,
            created_at=NOW - timedelta(days=age_days),
        )
    )
    session.commit()


def test_spend_is_priced_per_model(session: Session) -> None:
    # haiku: 1M in @ $1 + 1M out @ $5 = $6
    add_investigation(
        session,
        llm_calls=[
            {
                "model": "claude-haiku-4-5",
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
            }
        ],
    )

    status = llm_budget.get_budget_status(session, settings=budget_settings(), now=NOW)

    assert status.daily_spend_usd == pytest.approx(6.0)


def test_an_unknown_model_is_priced_conservatively(session: Session) -> None:
    """모르는 모델을 공짜로 취급하면 상한이 조용히 무력화된다."""
    add_investigation(
        session,
        llm_calls=[{"model": "some-new-model", "input_tokens": 1_000_000, "output_tokens": 0}],
    )

    status = llm_budget.get_budget_status(session, settings=budget_settings(), now=NOW)

    assert status.daily_spend_usd == pytest.approx(llm_budget.UNKNOWN_MODEL_RATE_USD_PER_MTOK[0])


def test_no_limits_means_never_exhausted(session: Session) -> None:
    add_investigation(
        session,
        llm_calls=[
            {"model": "claude-opus-4-8", "input_tokens": 10_000_000, "output_tokens": 10_000_000}
        ],
    )

    status = llm_budget.get_budget_status(session, settings=budget_settings(), now=NOW)

    assert status.exhausted is False


def test_the_daily_limit_trips(session: Session) -> None:
    add_investigation(
        session,
        llm_calls=[
            {"model": "claude-haiku-4-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000}
        ],
    )

    status = llm_budget.get_budget_status(session, settings=budget_settings(daily=5.0), now=NOW)

    assert status.exhausted is True
    assert status.reason is not None
    assert "daily" in status.reason


def test_spend_outside_the_day_does_not_trip_the_daily_limit(session: Session) -> None:
    add_investigation(
        session,
        llm_calls=[
            {"model": "claude-haiku-4-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000}
        ],
        age_days=2,
    )

    status = llm_budget.get_budget_status(
        session, settings=budget_settings(daily=5.0, monthly=100.0), now=NOW
    )

    assert status.daily_spend_usd == pytest.approx(0.0)
    assert status.monthly_spend_usd == pytest.approx(6.0)
    assert status.exhausted is False


def test_the_monthly_limit_trips_on_accumulated_spend(session: Session) -> None:
    for age in (1, 10, 20):
        add_investigation(
            session,
            llm_calls=[
                {
                    "model": "claude-haiku-4-5",
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                }
            ],
            age_days=age,
        )

    status = llm_budget.get_budget_status(session, settings=budget_settings(monthly=15.0), now=NOW)

    assert status.monthly_spend_usd == pytest.approx(18.0)
    assert status.exhausted is True
    assert status.reason is not None
    assert "monthly" in status.reason


def test_rates_can_be_overridden_without_a_deploy(session: Session) -> None:
    """단가는 앱보다 빨리 바뀐다."""
    add_investigation(
        session,
        llm_calls=[{"model": "claude-haiku-4-5", "input_tokens": 1_000_000, "output_tokens": 0}],
    )

    status = llm_budget.get_budget_status(
        session,
        settings=budget_settings(rates_json='{"claude-haiku-4-5": [2.0, 10.0]}'),
        now=NOW,
    )

    assert status.daily_spend_usd == pytest.approx(2.0)


def test_a_broken_rate_override_falls_back_to_the_built_in_table(session: Session) -> None:
    """설정 오타로 비용 계산이 죽으면 조사 전체가 멈춘다."""
    add_investigation(
        session,
        llm_calls=[{"model": "claude-haiku-4-5", "input_tokens": 1_000_000, "output_tokens": 0}],
    )

    status = llm_budget.get_budget_status(
        session, settings=budget_settings(rates_json="{not json"), now=NOW
    )

    assert status.daily_spend_usd == pytest.approx(1.0)


def test_investigations_without_llm_calls_cost_nothing(session: Session) -> None:
    add_investigation(session, llm_calls=[])

    status = llm_budget.get_budget_status(session, settings=budget_settings(), now=NOW)

    assert status.daily_spend_usd == pytest.approx(0.0)
