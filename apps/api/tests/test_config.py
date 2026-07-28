import pytest
from aim_api.config import (
    DEVELOPMENT_JWT_SECRET_KEY,
    MIN_JWT_SECRET_KEY_LENGTH,
    Settings,
)
from pydantic import ValidationError
from pytest import MonkeyPatch


def test_settings_read_environment_variables(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("ALERT_DELIVERY_BATCH_SIZE", "10")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.api_port == 9000
    assert settings.database_url == "postgresql+psycopg://test:test@localhost:5432/test"
    assert settings.jwt_secret_key == "test-secret"
    assert settings.jwt_access_token_expire_minutes == 15
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 2525
    assert settings.smtp_from_email == "alerts@example.com"
    assert settings.smtp_use_tls is False
    assert settings.alert_delivery_batch_size == 10


def test_development_defaults_do_not_require_a_jwt_secret() -> None:
    """로컬 개발은 아무 설정 없이 떠야 한다 — 가드가 개발을 막으면 안 된다."""
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.jwt_secret_key == DEVELOPMENT_JWT_SECRET_KEY


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_default_jwt_secret_is_rejected_outside_development(
    monkeypatch: MonkeyPatch, app_env: str
) -> None:
    """공개 저장소에 적힌 기본 키로 운영 부팅되는 것을 막는다."""
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="development default"):
        Settings(_env_file=None)


def test_short_jwt_secret_is_rejected_outside_development(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * (MIN_JWT_SECRET_KEY_LENGTH - 1))

    with pytest.raises(ValidationError, match="at least"):
        Settings(_env_file=None)


def test_strong_jwt_secret_is_accepted_in_production(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * MIN_JWT_SECRET_KEY_LENGTH)

    settings = Settings(_env_file=None)

    assert settings.app_env == "production"
