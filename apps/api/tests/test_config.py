from aim_api.config import Settings
from pytest import MonkeyPatch


def test_settings_read_environment_variables(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.api_port == 9000
