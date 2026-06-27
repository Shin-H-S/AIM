from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aim_api.models.scenario import TestScenario, TestStep
from aim_api.schemas.scenario import TestScenarioCreate, TestScenarioUpdate, TestStepCreate


class TestScenarioNotFoundError(Exception):
    """Raised when a test scenario does not exist for the requested project."""


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
    add_steps(session, scenario_id=scenario.id, steps=payload.steps)
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
        .order_by(TestScenario.created_at.desc(), TestScenario.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_scenario(
    session: Session,
    *,
    project_id: UUID,
    scenario_id: UUID,
) -> TestScenario:
    scenario = session.scalar(
        select(TestScenario).where(
            TestScenario.id == scenario_id,
            TestScenario.project_id == project_id,
        )
    )
    if scenario is None:
        raise TestScenarioNotFoundError

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


def delete_scenario(
    session: Session,
    *,
    project_id: UUID,
    scenario_id: UUID,
) -> None:
    scenario = get_scenario(session, project_id=project_id, scenario_id=scenario_id)
    session.delete(scenario)
    session.commit()


def list_steps(
    session: Session,
    *,
    scenario_id: UUID,
) -> list[TestStep]:
    return list(
        session.scalars(
            select(TestStep)
            .where(TestStep.scenario_id == scenario_id)
            .order_by(TestStep.step_order.asc())
        )
    )


def add_steps(
    session: Session,
    *,
    scenario_id: UUID,
    steps: list[TestStepCreate],
) -> None:
    for index, step in enumerate(steps, start=1):
        session.add(
            TestStep(
                scenario_id=scenario_id,
                step_order=index,
                action=step.action.value,
                target=step.target,
                value=step.value,
                timeout_ms=step.timeout_ms,
                is_critical=step.is_critical,
            )
        )


def replace_steps(
    session: Session,
    *,
    scenario_id: UUID,
    steps: list[TestStepCreate],
) -> None:
    session.execute(delete(TestStep).where(TestStep.scenario_id == scenario_id))
    add_steps(session, scenario_id=scenario_id, steps=steps)
