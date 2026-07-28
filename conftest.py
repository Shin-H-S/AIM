"""테스트 전역 픽스처 — 테스트용 데이터베이스와 API 클라이언트.

같은 엔진 생성 코드가 31개 테스트 파일에 복붙돼 있었다. 테스트 데이터베이스를
바꾸려면 31곳을 고쳐야 했고, 그래서 아무도 바꾸지 않았다. 여기로 모아 한 곳만
고치면 되게 한다.

파일별로 추가 설정이 필요하면(외부 호출 monkeypatch 등) 이 픽스처를 받아
자기 `client`/`session` 픽스처를 얹으면 된다.
"""

from collections.abc import Iterator

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def db_engine() -> Iterator[Engine]:
    """테스트 하나가 쓰는 데이터베이스. 스키마 생성과 폐기까지 책임진다."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def session_factory(db_engine: Engine) -> sessionmaker[Session]:
    """세션 팩토리. 요청마다 세션을 새로 여는 쪽(API 의존성, worker task)이 쓴다.

    expire_on_commit=False는 운영 SessionLocal과 맞춘 값이다 — 커밋 뒤에도
    객체 속성을 그대로 읽을 수 있어야 테스트가 운영과 같은 동작을 본다.
    """
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """서비스 계층을 직접 부르는 테스트가 쓰는 세션."""
    with session_factory() as testing_session:
        yield testing_session


@pytest.fixture()
def api_client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    """get_db가 테스트 데이터베이스를 보도록 덮어쓴 FastAPI 클라이언트."""

    def override_database() -> Iterator[Session]:
        with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db] = override_database

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
