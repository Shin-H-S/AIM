"""E2E 데이터베이스를 매 실행마다 새로 만든다.

Playwright의 webServer는 globalSetup보다 먼저 시작된다(실측). 그래서 DB 초기화를
globalSetup에 두면 API 서버의 alembic이 존재하지 않는 DB에 붙으려다 죽는다 —
초기화는 서버 기동 명령의 첫 단계여야 한다.

DROP/CREATE인 이유: 이 시점엔 아무 서버도 붙어 있지 않아 통째로 버리는 것이
가장 확실하고, 이전 실행의 어떤 상태도 새 실행에 스미지 않는다.
"""

import os
import sys
from urllib.parse import urlsplit

import psycopg

# 이 스크립트는 데이터베이스를 통째로 지운다. DATABASE_URL 오타 하나로 개발
# DB(aim)나 pytest DB(aim_test)를 날리는 사고를 이름 규칙으로 막는다.
REQUIRED_SUFFIX = "_e2e"


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://"))
    database_name = parsed.path.lstrip("/")

    if not database_name.endswith(REQUIRED_SUFFIX):
        print(
            f"refusing to drop {database_name!r}: E2E databases must end with "
            f"{REQUIRED_SUFFIX!r} so a mistyped DATABASE_URL cannot destroy a real one",
            file=sys.stderr,
        )
        return 1

    maintenance_url = database_url.replace(f"/{database_name}", "/postgres").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{database_name}"')

    print(f"e2e database {database_name} recreated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
