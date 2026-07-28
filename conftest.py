"""테스트 전역 픽스처 — 테스트용 데이터베이스와 API 클라이언트.

**테스트는 운영과 같은 PostgreSQL에서, 운영과 같은 마이그레이션으로 만든
스키마 위에서 돈다.** 이전에는 SQLite in-memory + `Base.metadata.create_all()`
이었는데, 그 조합은 두 가지를 통째로 검증 밖에 두었다:

1. 마이그레이션이 모델과 일치하는지 — 테스트가 create_all로 스키마를 만들면
   마이그레이션에 빠진 컬럼이 있어도 전부 통과한다.
2. PostgreSQL 고유 동작 — 제약 위반 시 트랜잭션 abort, timezone-aware
   timestamp, 정렬 시 NULL 순서, 행 잠금(FOR UPDATE)은 SQLite에서 다르거나
   아예 무시된다.

스키마는 세션당 한 번 `alembic upgrade head` 로 만들고, 테스트 사이에는
TRUNCATE로만 비운다. 테스트마다 마이그레이션을 다시 도는 것은 너무 느리다.
"""

import os
from collections.abc import Iterator

# aim_api.database 는 임포트 시점에 settings.database_url 로 엔진을 만든다.
# 그래서 aim_api 를 임포트하기 전에 테스트 DB를 가리키게 해야 한다 — 그러지
# 않으면 SessionLocal 이 운영 설정의 데이터베이스를 향한 채로 굳는다.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aim:aim@localhost:5432/aim_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# 레이트 리밋은 IP당 고정 윈도우다. 테스트는 전부 같은 IP(testclient)에서 수십 번
# 가입·로그인하므로, Redis가 **실제로 떠 있으면** 스위트가 한도를 넘어 429로
# 무너진다. 지금까지 통과한 이유는 Redis가 없어 rate limiter가 fail-open 했기
# 때문이지 격리가 돼 있어서가 아니었다 — 개발자가 `compose.dev.yaml up -d`로
# redis까지 띄우면 120건 넘게 실패한다.
#
# 레이트 리밋 자체는 test_rate_limit.py가 가짜 limiter로 직접 검증한다.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402
from aim_api.database import Base, get_db  # noqa: E402
from aim_api.main import app  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.util.exc import CommandError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

ALEMBIC_CONFIG_PATH = "migrations/alembic.ini"

MAINTENANCE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
TEST_DATABASE_NAME = TEST_DATABASE_URL.rsplit("/", 1)[1]


def run_maintenance_statement(statement: str) -> None:
    """CREATE/DROP DATABASE는 트랜잭션 안에서 못 돌아서 AUTOCOMMIT으로 연결한다."""
    engine = create_engine(MAINTENANCE_URL, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(statement))
    finally:
        engine.dispose()


def test_database_exists() -> bool:
    engine = create_engine(MAINTENANCE_URL, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            return bool(
                connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": TEST_DATABASE_NAME},
                )
            )
    finally:
        engine.dispose()


def recreate_test_database() -> None:
    run_maintenance_statement(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}" WITH (FORCE)')
    run_maintenance_statement(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')


def ensure_test_database_exists() -> None:
    if not test_database_exists():
        run_maintenance_statement(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    """마이그레이션 헤드까지 올린 테스트 데이터베이스 엔진.

    `create_all` 이 아니라 Alembic으로 만드는 것이 핵심이다 — 테스트가 도는
    스키마가 운영에 배포되는 스키마와 같은 절차로 생성된다.
    """
    ensure_test_database_exists()

    alembic_config = Config(ALEMBIC_CONFIG_PATH)
    alembic_config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    try:
        # 이전 실행이 남긴 스키마가 있어도 헤드까지만 맞추면 된다.
        command.upgrade(alembic_config, "head")
    except CommandError:
        # 테스트 DB에 이 브랜치에 없는 리비전이 찍혀 있다 — 마이그레이션을 추가한
        # 다른 브랜치에서 테스트를 돌린 뒤 넘어오면 늘 이렇게 된다. Alembic은
        # 그 리비전을 못 찾아 "Can't locate revision"으로 멈추는데, 원인이
        # 드러나지 않아 브랜치를 옮길 때마다 사람을 붙잡는다.
        # 테스트 데이터베이스는 정의상 언제 버려도 되는 것이라 다시 만든다.
        recreate_test_database()
        command.upgrade(alembic_config, "head")

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


def truncate_all_tables(engine: Engine) -> None:
    """테스트 사이 격리. alembic_version은 남겨 스키마를 다시 만들지 않는다."""
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    if not table_names:
        return

    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def db_engine(migrated_engine: Engine) -> Iterator[Engine]:
    """테스트 하나가 쓰는 데이터베이스. 끝나면 모든 테이블을 비운다."""
    try:
        yield migrated_engine
    finally:
        truncate_all_tables(migrated_engine)


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
