from aim_api.config import Settings
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
