from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aim_api.models.scenario import (
    ScenarioRun,
    ScenarioRunStatus,
    StepResult,
    StepResultStatus,
    TestScenario,
    TestStep,
)
from aim_api.schemas.scenario import TestScenarioCreate, TestScenarioUpdate, TestStepCreate


class ScenarioNotFoundError(Exception):
    """Raised when a test scenario does not exist for the requested project."""


class ScenarioRunNotFoundError(Exception):
    """Raised when a scenario run does not exist for the requested project."""


class ScenarioInactiveError(Exception):
    """Raised when an inactive scenario is requested to run."""


def calculate_duration_ms(*, started_at: datetime, finished_at: datetime) -> int:
    if started_at.tzinfo is None and finished_at.tzinfo is not None:
        finished_at = finished_at.replace(tzinfo=None)
    if started_at.tzinfo is not None and finished_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)

    return int((finished_at - started_at).total_seconds() * 1000)


def build_step(*, scenario_id: UUID, step_order: int, payload: TestStepCreate) -> TestStep:
    return TestStep(
        scenario_id=scenario_id,
        step_order=step_order,
        action=payload.action.value,
        target=payload.target,
        value=payload.value,
        timeout_ms=payload.timeout_ms,
        is_critical=payload.is_critical,
    )


def replace_steps(
    session: Session,
    *,
    scenario_id: UUID,
    steps: list[TestStepCreate],
) -> None:
    session.execute(delete(TestStep).where(TestStep.scenario_id == scenario_id))
    for index, step_payload in enumerate(steps, start=1):
        session.add(build_step(scenario_id=scenario_id, step_order=index, payload=step_payload))


def create_scenario(
    session: Session,
    *,
    project_id: UUID,
    payload: TestScenarioCreate,
) -> TestScenario:
    scenario = TestScenario(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(scenario)
    session.flush()
    replace_steps(session, scenario_id=scenario.id, steps=payload.steps)
    session.commit()
    session.refresh(scenario)
    return scenario


def list_scenarios(
    session: Session,
    *,
    project_id: UUID,
    limit: int,
    offset: int,
) -> list[TestScenario]:
    statement = (
        select(TestScenario)
        .where(TestScenario.project_id == project_id)
        .order_by(TestScenario.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_scenario(session: Session, *, project_id: UUID, scenario_id: UUID) -> TestScenario:
    statement = select(TestScenario).where(
        TestScenario.id == scenario_id,
        TestScenario.project_id == project_id,
    )
    scenario = session.scalar(statement)
    if scenario is None:
        raise ScenarioNotFoundError

    return scenario


def update_scenario(
    session: Session,
    *,
    project_id: UUID,
    scenario_id: UUID,
    payload: TestScenarioUpdate,
) -> TestScenario:
    scenario = get_scenario(session, project_id=project_id, scenario_id=scenario_id)
    updated_fields = payload.model_fields_set

    if "name" in updated_fields and payload.name is not None:
        scenario.name = payload.name
    if "description" in updated_fields:
        scenario.description = payload.description
    if "is_active" in updated_fields and payload.is_active is not None:
        scenario.is_active = payload.is_active
    if "steps" in updated_fields and payload.steps is not None:
        replace_steps(session, scenario_id=scenario.id, steps=payload.steps)

    session.commit()
    session.refresh(scenario)
    return scenario


def delete_scenario(session: Session, *, project_id: UUID, scenario_id: UUID) -> None:
    scenario = get_scenario(session, project_id=project_id, scenario_id=scenario_id)
    session.delete(scenario)
    session.commit()


def list_steps(session: Session, *, scenario_id: UUID) -> list[TestStep]:
    statement = (
        select(TestStep)
        .where(TestStep.scenario_id == scenario_id)
        .order_by(TestStep.step_order.asc())
    )
    return list(session.scalars(statement))


def create_scenario_run(
    session: Session,
    *,
    project_id: UUID,
    scenario_id: UUID,
    requested_by_id: UUID,
) -> ScenarioRun:
    scenario = get_scenario(session, project_id=project_id, scenario_id=scenario_id)
    if not scenario.is_active:
        raise ScenarioInactiveError

    scenario_run = ScenarioRun(
        project_id=project_id,
        scenario_id=scenario_id,
        requested_by_id=requested_by_id,
        status=ScenarioRunStatus.QUEUED.value,
        trigger_source="manual",
    )
    session.add(scenario_run)
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def list_scenario_runs(
    session: Session,
    *,
    project_id: UUID,
    scenario_id: UUID,
    limit: int,
    offset: int,
) -> list[ScenarioRun]:
    statement = (
        select(ScenarioRun)
        .where(
            ScenarioRun.project_id == project_id,
            ScenarioRun.scenario_id == scenario_id,
        )
        .order_by(ScenarioRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_scenario_run(
    session: Session,
    *,
    project_id: UUID,
    scenario_id: UUID,
    scenario_run_id: UUID,
) -> ScenarioRun:
    statement = select(ScenarioRun).where(
        ScenarioRun.id == scenario_run_id,
        ScenarioRun.project_id == project_id,
        ScenarioRun.scenario_id == scenario_id,
    )
    scenario_run = session.scalar(statement)
    if scenario_run is None:
        raise ScenarioRunNotFoundError

    return scenario_run


def get_scenario_run_by_id(session: Session, *, scenario_run_id: UUID) -> ScenarioRun:
    scenario_run = session.get(ScenarioRun, scenario_run_id)
    if scenario_run is None:
        raise ScenarioRunNotFoundError

    return scenario_run


def mark_scenario_run_running(session: Session, *, scenario_run_id: UUID) -> ScenarioRun:
    scenario_run = get_scenario_run_by_id(session, scenario_run_id=scenario_run_id)
    if scenario_run.status in {
        ScenarioRunStatus.COMPLETED.value,
        ScenarioRunStatus.FAILED.value,
        ScenarioRunStatus.CANCELLED.value,
    }:
        return scenario_run

    scenario_run.status = ScenarioRunStatus.RUNNING.value
    if scenario_run.started_at is None:
        scenario_run.started_at = datetime.now(UTC)
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def mark_scenario_run_failed(
    session: Session,
    *,
    scenario_run_id: UUID,
    failure_reason: str,
) -> ScenarioRun:
    scenario_run = get_scenario_run_by_id(session, scenario_run_id=scenario_run_id)
    if scenario_run.status in {
        ScenarioRunStatus.COMPLETED.value,
        ScenarioRunStatus.CANCELLED.value,
    }:
        return scenario_run

    finished_at = datetime.now(UTC)
    scenario_run.status = ScenarioRunStatus.FAILED.value
    scenario_run.failure_reason = failure_reason
    scenario_run.finished_at = finished_at
    if scenario_run.started_at is not None:
        scenario_run.duration_ms = calculate_duration_ms(
            started_at=scenario_run.started_at,
            finished_at=finished_at,
        )
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def mark_scenario_run_completed(session: Session, *, scenario_run_id: UUID) -> ScenarioRun:
    scenario_run = get_scenario_run_by_id(session, scenario_run_id=scenario_run_id)
    if scenario_run.status in {
        ScenarioRunStatus.FAILED.value,
        ScenarioRunStatus.CANCELLED.value,
    }:
        return scenario_run

    finished_at = datetime.now(UTC)
    scenario_run.status = ScenarioRunStatus.COMPLETED.value
    scenario_run.failure_reason = None
    scenario_run.finished_at = finished_at
    if scenario_run.started_at is not None:
        scenario_run.duration_ms = calculate_duration_ms(
            started_at=scenario_run.started_at,
            finished_at=finished_at,
        )
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def record_step_result(
    session: Session,
    *,
    scenario_run_id: UUID,
    test_step_id: UUID | None,
    step_order: int,
    action: str,
    target: str | None,
    status: StepResultStatus,
    started_at: datetime | None,
    finished_at: datetime | None,
    duration_ms: int | None,
    error_message: str | None,
) -> StepResult:
    step_result = StepResult(
        scenario_run_id=scenario_run_id,
        test_step_id=test_step_id,
        step_order=step_order,
        action=action,
        target=target,
        status=status.value,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        error_message=error_message,
    )
    session.add(step_result)
    session.commit()
    session.refresh(step_result)
    return step_result


def clear_step_results(session: Session, *, scenario_run_id: UUID) -> None:
    session.execute(delete(StepResult).where(StepResult.scenario_run_id == scenario_run_id))
    session.commit()


def list_step_results(session: Session, *, scenario_run_id: UUID) -> list[StepResult]:
    statement = (
        select(StepResult)
        .where(StepResult.scenario_run_id == scenario_run_id)
        .order_by(StepResult.step_order.asc())
    )
    return list(session.scalars(statement))
