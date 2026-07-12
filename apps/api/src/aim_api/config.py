from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    app_env: str = "development"
    app_log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    database_url: str = "postgresql+psycopg://aim:aim@localhost:5432/aim"
    redis_url: str = "redis://localhost:6379/0"
    scanner_timeout_seconds: float = 10.0
    scanner_max_redirects: int = 5
    scanner_max_response_bytes: int = 1_048_576
    ssl_inspection_timeout_seconds: float = 10.0
    lighthouse_command: str = "corepack pnpm exec lighthouse"
    lighthouse_timeout_seconds: int = 180
    artifact_storage_backend: str = "local"
    artifact_local_root: str = "artifacts"
    scan_scheduler_interval_seconds: int = 60
    jwt_secret_key: str = "replace-with-a-local-development-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    password_reset_token_expire_minutes: int = 30
    # 비인증 엔드포인트(로그인·가입·재설정·배포 훅)의 IP당 분당 한도 사용 여부.
    rate_limit_enabled: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = 10.0
    alert_delivery_batch_size: int = 25
    alert_webhook_timeout_seconds: float = 10.0
    # 알림 본문에 넣을 웹 UI 기본 URL (예: https://qaaimsync.com). 없으면 링크를 생략한다.
    web_base_url: str | None = None
    anthropic_api_key: str | None = None
    ai_report_model: str = "claude-opus-4-8"
    ai_report_llm_timeout_seconds: float = 30.0
    ai_report_llm_max_retries: int = 1
    ai_report_llm_max_tokens: int = 16000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
