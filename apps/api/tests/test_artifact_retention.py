from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.alert import Incident, IncidentStatus
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus, TestScenario
from aim_api.models.user import User
from aim_api.services import artifact_retention
from sqlalchemy import select
from sqlalchemy.orm import Session

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
POLICY = artifact_retention.ArtifactRetentionPolicy(default_days=14, incident_days=90)


def create_project(session: Session) -> Project:
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
    return project


def create_check_run(
    session: Session,
    *,
    project: Project,
    status: str = CheckRunStatus.COMPLETED.value,
) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=status,
        trigger_source="manual",
    )
    session.add(check_run)
    session.flush()
    return check_run


def add_artifact(
    session: Session,
    *,
    age_days: int,
    check_run_id: UUID | None = None,
    scenario_run_id: UUID | None = None,
) -> Artifact:
    artifact = Artifact(
        check_run_id=check_run_id,
        scenario_run_id=scenario_run_id,
        artifact_type="lighthouse_json",
        storage_backend="local",
        storage_path=f"check-runs/{check_run_id or scenario_run_id}/{uuid4()}.json",
        content_type="application/json",
        size_bytes=10,
        checksum_sha256="0" * 64,
        created_at=NOW - timedelta(days=age_days),
    )
    session.add(artifact)
    session.commit()
    return artifact


def expired_ids(session: Session) -> set[UUID]:
    artifacts = artifact_retention.list_expired_artifacts(
        session, now=NOW, policy=POLICY, limit=100
    )
    return {artifact.id for artifact in artifacts}


def test_recent_artifacts_are_kept(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    artifact = add_artifact(session, age_days=13, check_run_id=check_run.id)

    assert artifact.id not in expired_ids(session)


def test_ordinary_artifacts_expire_after_the_default_period(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    artifact = add_artifact(session, age_days=15, check_run_id=check_run.id)

    assert artifact.id in expired_ids(session)


def test_baseline_check_run_artifacts_are_never_expired(session: Session) -> None:
    """베이스라인은 비교의 기준점이라 나이와 무관하게 남아야 한다."""
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    project.baseline_check_run_id = check_run.id
    session.commit()
    artifact = add_artifact(session, age_days=1000, check_run_id=check_run.id)

    assert artifact.id not in expired_ids(session)


def test_failed_check_run_artifacts_survive_the_default_period(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project, status=CheckRunStatus.FAILED.value)
    artifact = add_artifact(session, age_days=30, check_run_id=check_run.id)

    assert artifact.id not in expired_ids(session)


def test_failed_check_run_artifacts_expire_after_the_incident_period(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project, status=CheckRunStatus.FAILED.value)
    artifact = add_artifact(session, age_days=91, check_run_id=check_run.id)

    assert artifact.id in expired_ids(session)


def test_incident_check_run_artifacts_survive_the_default_period(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    session.add(
        Incident(
            project_id=project.id,
            opened_check_run_id=check_run.id,
            trigger_type="SERVICE_CONNECTION_FAILURE",
            severity="RISK",
            status=IncidentStatus.OPEN.value,
            title="Service is down",
            summary="Connection refused",
            started_at=NOW,
        )
    )
    session.commit()
    artifact = add_artifact(session, age_days=30, check_run_id=check_run.id)

    assert artifact.id not in expired_ids(session)


def test_investigated_check_run_artifacts_survive_the_default_period(session: Session) -> None:
    """조사가 참조한 근거가 사라지면 조사 결론을 다시 검증할 수 없다."""
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    session.add(
        AgentInvestigation(
            project_id=project.id,
            check_run_id=check_run.id,
            trigger="incident",
            root_cause="service_down",
            confidence="high",
            summary="The service did not respond.",
            recommendation="Check the origin server.",
            generator="rule",
            recheck_used=False,
            duration_ms=1200,
        )
    )
    session.commit()
    artifact = add_artifact(session, age_days=30, check_run_id=check_run.id)

    assert artifact.id not in expired_ids(session)


def create_scenario_run(
    session: Session,
    *,
    project: Project,
    status: str,
    check_run_id: UUID | None = None,
) -> ScenarioRun:
    scenario = TestScenario(
        project_id=project.id,
        name="Login flow",
    )
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        requested_by_id=project.owner_id,
        check_run_id=check_run_id,
        status=status,
    )
    session.add(scenario_run)
    session.flush()
    return scenario_run


def test_scenario_run_artifacts_follow_the_linked_check_run(session: Session) -> None:
    """검사에 연결된 시나리오 실행의 근거는 그 검사의 등급을 따라야 한다."""
    project = create_project(session)
    check_run = create_check_run(session, project=project, status=CheckRunStatus.FAILED.value)
    scenario_run = create_scenario_run(
        session,
        project=project,
        status=ScenarioRunStatus.COMPLETED.value,
        check_run_id=check_run.id,
    )
    artifact = add_artifact(session, age_days=30, scenario_run_id=scenario_run.id)

    assert artifact.id not in expired_ids(session)


def test_failed_standalone_scenario_run_artifacts_survive_the_default_period(
    session: Session,
) -> None:
    project = create_project(session)
    scenario_run = create_scenario_run(
        session, project=project, status=ScenarioRunStatus.FAILED.value
    )
    artifact = add_artifact(session, age_days=30, scenario_run_id=scenario_run.id)

    assert artifact.id not in expired_ids(session)


def test_passing_standalone_scenario_run_artifacts_expire_normally(session: Session) -> None:
    project = create_project(session)
    scenario_run = create_scenario_run(
        session, project=project, status=ScenarioRunStatus.COMPLETED.value
    )
    artifact = add_artifact(session, age_days=15, scenario_run_id=scenario_run.id)

    assert artifact.id in expired_ids(session)


def test_expired_artifacts_are_returned_oldest_first_within_the_limit(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    oldest = add_artifact(session, age_days=40, check_run_id=check_run.id)
    add_artifact(session, age_days=30, check_run_id=check_run.id)

    artifacts = artifact_retention.list_expired_artifacts(session, now=NOW, policy=POLICY, limit=1)

    assert [artifact.id for artifact in artifacts] == [oldest.id]


def test_delete_artifact_record_removes_the_row(session: Session) -> None:
    project = create_project(session)
    check_run = create_check_run(session, project=project)
    artifact = add_artifact(session, age_days=15, check_run_id=check_run.id)

    artifact_retention.delete_artifact_record(session, artifact_id=artifact.id)

    assert session.scalar(select(Artifact).where(Artifact.id == artifact.id)) is None


def test_delete_artifact_record_is_idempotent(session: Session) -> None:
    """파일은 지웠는데 레코드 삭제가 중복 호출돼도 실패하면 안 된다."""
    artifact_retention.delete_artifact_record(session, artifact_id=uuid4())


def test_incident_retention_shorter_than_default_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be shorter"):
        artifact_retention.ArtifactRetentionPolicy(default_days=30, incident_days=14)


def test_zero_retention_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one day"):
        artifact_retention.ArtifactRetentionPolicy(default_days=0, incident_days=90)
