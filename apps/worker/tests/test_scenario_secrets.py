from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from aim_api.config import Settings
from aim_api.models.scenario import TestStep
from aim_worker import playwright_runner, scenario_secrets
from aim_worker.scenario_secrets import ScenarioSecretError, resolve_secret_references


@pytest.fixture(autouse=True)
def without_secrets_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scenario_secrets,
        "get_settings",
        lambda: Settings(scenario_secrets_file=None),
    )


def use_secrets_file(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(
        scenario_secrets,
        "get_settings",
        lambda: Settings(scenario_secrets_file=str(path)),
    )


def test_resolves_secret_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCENARIO_SECRET_LOGIN_PASSWORD", "s3cret-value")

    assert resolve_secret_references("{{secret:LOGIN_PASSWORD}}") == "s3cret-value"


def test_resolves_multiple_references_inside_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCENARIO_SECRET_FIRST", "one")
    monkeypatch.setenv("SCENARIO_SECRET_SECOND", "two")

    resolved = resolve_secret_references("x-{{secret:FIRST}}-{{ secret:SECOND }}-y")

    assert resolved == "x-one-two-y"


def test_plain_values_pass_through_unchanged() -> None:
    assert resolve_secret_references("plain visible value") == "plain visible value"


def test_missing_secret_fails_with_name_but_never_a_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCENARIO_SECRET_MISSING", raising=False)

    with pytest.raises(ScenarioSecretError) as exc_info:
        resolve_secret_references("{{secret:MISSING}}")

    assert "SCENARIO_SECRET_MISSING" in str(exc_info.value)


def test_falls_back_to_secrets_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets_file = tmp_path / "scenario-secrets.env"
    secrets_file.write_text(
        "# 주석과 빈 줄은 무시된다\n\nLOGIN_PASSWORD=from-file\nOTHER=unused\n",
        encoding="utf-8",
    )
    use_secrets_file(monkeypatch, secrets_file)
    monkeypatch.delenv("SCENARIO_SECRET_LOGIN_PASSWORD", raising=False)

    assert resolve_secret_references("{{secret:LOGIN_PASSWORD}}") == "from-file"


def test_environment_wins_over_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets_file = tmp_path / "scenario-secrets.env"
    secrets_file.write_text("LOGIN_PASSWORD=from-file\n", encoding="utf-8")
    use_secrets_file(monkeypatch, secrets_file)
    monkeypatch.setenv("SCENARIO_SECRET_LOGIN_PASSWORD", "from-env")

    assert resolve_secret_references("{{secret:LOGIN_PASSWORD}}") == "from-env"


def test_unreadable_file_counts_as_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_secrets_file(monkeypatch, tmp_path / "does-not-exist.env")
    monkeypatch.delenv("SCENARIO_SECRET_LOGIN_PASSWORD", raising=False)

    with pytest.raises(ScenarioSecretError):
        resolve_secret_references("{{secret:LOGIN_PASSWORD}}")


class RecordingLocator:
    def __init__(self) -> None:
        self.fills: list[tuple[str, int]] = []

    def fill(self, value: str, *, timeout: int) -> None:
        self.fills.append((value, timeout))

    def click(self, *, timeout: int) -> None:
        raise AssertionError("click should not be called")

    def count(self) -> int:
        return 1

    def inner_text(self, *, timeout: int) -> str:
        raise AssertionError("inner_text should not be called")


class SingleLocatorPage:
    def __init__(self) -> None:
        self.target_locator = RecordingLocator()
        self.url = "https://example.com"

    def goto(
        self,
        url: str,
        *,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None,
        timeout: float | None,
    ) -> object:
        raise AssertionError("goto should not be called")

    def locator(self, selector: str) -> RecordingLocator:
        _ = selector
        return self.target_locator

    def wait_for_timeout(self, timeout: int) -> None:
        raise AssertionError("wait should not be called")

    def wait_for_url(self, url: object, *, timeout: float | None) -> None:
        raise AssertionError("wait_for_url should not be called")

    def screenshot(self, *, full_page: bool) -> bytes:
        raise AssertionError("screenshot should not be called")


def build_fill_step(value: str) -> TestStep:
    return TestStep(
        id=uuid4(),
        scenario_id=uuid4(),
        step_order=1,
        action="fill",
        target="#password",
        value=value,
        timeout_ms=None,
        is_critical=True,
    )


def test_fill_step_injects_secret_at_execution_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCENARIO_SECRET_LOGIN_PASSWORD", "runtime-only")
    page = SingleLocatorPage()

    playwright_runner.execute_step(page, build_fill_step("{{secret:LOGIN_PASSWORD}}"))

    assert page.target_locator.fills == [("runtime-only", 10_000)]


def test_fill_step_fails_when_secret_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCENARIO_SECRET_NOPE", raising=False)
    page = SingleLocatorPage()

    with pytest.raises(ScenarioSecretError, match="SCENARIO_SECRET_NOPE"):
        playwright_runner.execute_step(page, build_fill_step("{{secret:NOPE}}"))

    assert page.target_locator.fills == []
