from collections.abc import Iterator
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.project import Project
from aim_api.models.scanner_result import AvailabilityResult, LighthouseResult
from aim_api.models.user import User
from aim_api.schemas.project import ProjectCreate, ProjectUpdate, ScoringPreset
from aim_api.services import projects as project_service
from aim_api.services.score_results import (
    DEFAULT_SCORING_PRESET,
    SCORING_PRESETS,
    calculate_score,
    calculate_weighted_score,
    get_preset_weights,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_every_preset_weight_sums_to_100() -> None:
    for preset, weights in SCORING_PRESETS.items():
        assert sum(weights.values()) == 100, preset


def test_unknown_preset_falls_back_to_default() -> None:
    assert get_preset_weights("nonsense") == SCORING_PRESETS[DEFAULT_SCORING_PRESET]


def test_weighted_score_skips_zero_weight_categories() -> None:
    scores: dict[str, int | None] = {
        "availability_score": 100,
        "functional_stability_score": None,
        "web_performance_score": 60,
        "accessibility_score": 100,
        "seo_basic_quality_score": 100,
        "regression_stability_score": None,
    }

    service_score, service_weight = calculate_weighted_score(
        scores, weights=get_preset_weights("service")
    )
    content_score, content_weight = calculate_weighted_score(
        scores, weights=get_preset_weights("content")
    )
    internal_score, internal_weight = calculate_weighted_score(
        scores, weights=get_preset_weights("internal")
    )

    assert (service_score, service_weight) == (87, 60)
    assert (content_score, content_weight) == (85, 80)
    # 내부 도구형은 SEO 가중치가 0이라 수집돼도 반영되지 않는다.
    assert (internal_score, internal_weight) == (89, 55)


def build_project(preset: str) -> Project:
    return Project(
        id=uuid4(),
        owner_id=uuid4(),
        name="AIM Website",
        service_url="https://example.com",
        environment="production",
        scoring_preset=preset,
        response_time_threshold_ms=1_000,
        quality_score_threshold=80,
    )


def build_scan_results(project: Project) -> tuple[AvailabilityResult, LighthouseResult]:
    availability = AvailabilityResult(
        check_run_id=uuid4(),
        service_url=project.service_url,
        final_url=project.service_url,
        is_available=True,
        status_code=200,
        response_time_ms=500,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
    )
    lighthouse = LighthouseResult(
        check_run_id=uuid4(),
        service_url=project.service_url,
        is_successful=True,
        performance_score=60,
        accessibility_score=100,
        seo_score=100,
        best_practices_score=100,
    )
    return availability, lighthouse


def test_calculate_score_uses_project_preset_and_records_it() -> None:
    project = build_project("internal")
    availability, lighthouse = build_scan_results(project)

    calculated = calculate_score(
        project=project,
        availability_result=availability,
        ssl_result=None,
        lighthouse_result=lighthouse,
    )

    assert calculated.overall_score == 89
    assert calculated.evaluated_weight == 55
    assert calculated.score_breakdown is not None
    assert calculated.score_breakdown["preset"] == "internal"
    seo_category = next(
        category
        for category in calculated.score_breakdown["categories"]
        if category["key"] == "seo_basic_quality"
    )
    assert seo_category["weight"] == 0


def test_calculate_score_default_preset_matches_previous_weights() -> None:
    project = build_project("service")
    availability, lighthouse = build_scan_results(project)

    calculated = calculate_score(
        project=project,
        availability_result=availability,
        ssl_result=None,
        lighthouse_result=lighthouse,
    )

    assert calculated.overall_score == 87
    assert calculated.evaluated_weight == 60
    assert calculated.score_breakdown is not None
    assert calculated.score_breakdown["preset"] == "service"


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


def create_owner(session: Session) -> User:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_project_create_defaults_to_service_preset(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
    owner = create_owner(session)

    project = project_service.create_project(
        session,
        owner_id=owner.id,
        payload=ProjectCreate(name="Blog", service_url="https://example.com"),
    )

    assert project.scoring_preset == "service"


def test_project_preset_can_be_created_and_updated(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
    owner = create_owner(session)

    project = project_service.create_project(
        session,
        owner_id=owner.id,
        payload=ProjectCreate(
            name="Blog",
            service_url="https://example.com",
            scoring_preset=ScoringPreset.CONTENT,
        ),
    )
    assert project.scoring_preset == "content"

    updated = project_service.update_project(
        session,
        owner_id=owner.id,
        project_id=project.id,
        payload=ProjectUpdate(scoring_preset=ScoringPreset.INTERNAL),
    )
    assert updated.scoring_preset == "internal"
