import os
import re
from pathlib import Path

from aim_api.config import get_settings
from aim_api.schemas.scenario import SECRET_REFERENCE_PATTERN

SECRET_ENV_PREFIX = "SCENARIO_SECRET_"


class ScenarioSecretError(RuntimeError):
    """시크릿 참조를 해석할 수 없을 때 — 메시지에 시크릿 값은 절대 넣지 않는다."""


def resolve_secret_references(value: str) -> str:
    """fill 값의 {{secret:NAME}} 참조를 실제 값으로 치환한다.

    실제 값은 SCENARIO_SECRET_<NAME> 환경변수에서 먼저 찾고, 없으면
    settings.scenario_secrets_file(NAME=VALUE 형식)에서 찾는다. 둘 다 없으면
    조용히 빈 값을 넣는 대신 스텝을 실패시켜 원인이 바로 보이게 한다.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = lookup_secret(name)
        if resolved is None:
            raise ScenarioSecretError(
                f"Scenario secret {SECRET_ENV_PREFIX}{name} is not configured."
            )
        return resolved

    return SECRET_REFERENCE_PATTERN.sub(replace, value)


def lookup_secret(name: str) -> str | None:
    env_value = os.environ.get(f"{SECRET_ENV_PREFIX}{name}")
    if env_value:
        return env_value

    return lookup_secret_from_file(name)


def lookup_secret_from_file(name: str) -> str | None:
    secrets_file = get_settings().scenario_secrets_file
    if not secrets_file:
        return None

    path = Path(secrets_file)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip() or None

    return None
