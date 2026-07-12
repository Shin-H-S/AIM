from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import ScoreResult
from aim_api.models.user import User
from aim_api.services import scanner_results, score_results
from aim_api.services.score_results import regression_stability_score_with_reasons
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

CURRENT_SCORES: dict[str, int | None] = {
    "availability_score": 100,
    "functional_stability_score": None,
    "web_performance_score": 90,
    "accessibility_score": 95,
    "seo_basic_quality_score": 90,
}


def build_previous(**overrides: int | None) -> ScoreResult:
    values: dict[str, int | None] = {
        "availability_score": 100,
        "functional_stability_score": None,
        "web_performance_score": 90,
        "accessibility_score": 95,
        "seo_basic_quality_score": 90,
    }
    values.update(overrides)
    return ScoreResult(check_run_id=uuid4(), **values)


def test_no_previous_run_is_excluded() -> None:
    score, reasons = regression_stability_score_with_reasons(
        current_scores=CURRENT_SCORES,
        previous_score_result=None,
    )

    assert score is None
    assert reasons == [{"code": "no_previous_run"}]


def test_no_regressions_scores_full_marks() -> None:
    score, reasons = regression_stability_score_with_reasons(
        current_scores=CURRENT_SCORES,
        previous_score_result=build_previous(),
    )

    assert score == 100
    assert reasons == [{"code": "no_regressions", "compared": 4}]


def test_improvements_do_not_penalize() -> None:
    score, _ = regression_stability_score_with_reasons(
        current_scores=CURRENT_SCORES,
        previous_score_result=build_previous(web_performance_score=60),
    )

    assert score == 100


def test_category_drops_are_penalized_double() -> None:
    score, reasons = regression_stability_score_with_reasons(
        current_scores=CURRENT_SCORES,
        previous_score_result=build_previous(
            web_performance_score=100,
            accessibility_score=100,
        ),
    )

    # 웹 성능 10점 + 접근성 5점 하락 → 15점 하락 × 2배 = -30점.
    assert score == 70
    assert reasons == [
        {
            "code": "category_regressions",
            "points": -30,
            "total_drop": 15,
            "regressed": [
                {"category": "web_performance", "drop": 10},
                {"category": "accessibility", "drop": 5},
            ],
        }
    ]


def test_penalty_is_floored_at_zero() -> None:
    score, _ = regression_stability_score_with_reasons(
        current_scores={**CURRENT_SCORES, "web_performance_score": 0},
        previous_score_result=build_previous(web_performance_score=100),
    )

    assert score == 0


def test_categories_missing_on_either_side_are_skipped() -> None:
    score, reasons = regression_stability_score_with_reasons(
        current_scores={
            "availability_score": 100,
            "functional_stability_score": None,
            "web_performance_score": None,
            "accessibility_score": None,
            "seo_basic_quality_score": None,
        },
        previous_score_result=build_previous(availability_score=None),
    )

    assert score is None
    assert reasons == [{"code": "no_comparable_categories"}]


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_project(session: Session) -> Project:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC),
        environment="production",
        response_time_threshold_ms=1_000,
        quality_score_threshold=80,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def record_run_with_score(
    session: Session,
    *,
    project: Project,
    created_at: datetime,
    response_time_ms: int,
) -> ScoreResult:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="manual",
        created_at=created_at,
    )
    session.add(check_run)
    session.commit()
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url=project.service_url,
        final_url=project.service_url,
        is_available=True,
        status_code=200,
        response_time_ms=response_time_ms,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )
    return score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )


def test_second_run_scores_regression_against_the_first(session: Session) -> None:
    project = create_project(session)
    base_time = datetime.now(UTC)

    first = record_run_with_score(
        session,
        project=project,
        created_at=base_time - timedelta(hours=1),
        response_time_ms=200,
    )
    assert first.regression_stability_score is None
    assert first.evaluated_weight == 25

    # 두 번째 검사는 응답 시간 임계값 초과로 가용성이 100 → 80으로 하락한다.
    second = record_run_with_score(
        session,
        project=project,
        created_at=base_time,
        response_time_ms=1_500,
    )

    assert second.availability_score == 80
    # 가용성 20점 하락 × 2배 = 60점.
    assert second.regression_stability_score == 60
    # 회귀 안정성(10%)이 이제 평가에 포함된다.
    assert second.evaluated_weight == 35
    breakdown_by_key = {
        category["key"]: category for category in (second.score_breakdown or {})["categories"]
    }
    assert breakdown_by_key["regression_stability"]["score"] == 60
