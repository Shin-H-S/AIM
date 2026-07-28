from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 로컬 개발용 기본 서명 키. 이 값은 공개 저장소에 그대로 적혀 있으므로,
# 운영 환경에서 이 키로 토큰을 서명하면 누구나 임의 사용자를 사칭할 수 있다.
DEVELOPMENT_JWT_SECRET_KEY = "replace-with-a-local-development-secret"

# 서명 키를 강제하지 않는 환경. 그 외(production·staging 등)는 부팅을 막는다.
UNGUARDED_APP_ENVS = frozenset({"development", "test"})

# HS256 서명 키의 최소 길이. 해시 출력이 256비트이므로 그보다 짧은 키를 쓰면
# 알고리즘이 보장하는 강도를 얻지 못한다.
MIN_JWT_SECRET_KEY_LENGTH = 32


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
    # 아티팩트 보존 기간. 단일 VM 디스크에 무한히 쌓이는 것을 막는다.
    # 이상 없이 끝난 검사의 근거는 오래 들고 있을 이유가 적다.
    artifact_retention_days: int = 14
    # 장애·실패·조사가 걸린 검사의 근거는 훨씬 오래 남긴다 — 사후 분석의 대상이다.
    # 베이스라인 검사의 근거는 기간과 무관하게 보존한다(비교 기준점이므로).
    artifact_incident_retention_days: int = 90
    # 정리 태스크 1회가 지우는 최대 아티팩트 수. 한 번에 오래 잡고 있지 않게 나눈다.
    artifact_purge_batch_size: int = 500
    scan_scheduler_interval_seconds: int = 60
    jwt_secret_key: str = DEVELOPMENT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    password_reset_token_expire_minutes: int = 30
    # 가입 인증 메일 링크 유효 시간. 재발송 수단이 있으므로 하루면 충분하다.
    email_verification_token_expire_minutes: int = 60 * 24
    # 비인증 엔드포인트(로그인·가입·재설정·배포 훅)의 IP당 분당 한도 사용 여부.
    rate_limit_enabled: bool = True
    # 시나리오 {{secret:NAME}} 참조를 해석할 NAME=VALUE 형식 파일 (환경변수보다 후순위).
    scenario_secrets_file: str | None = None
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
    # AIM 자신의 장애(미처리 예외·태스크 실패)를 운영자에게 알릴 incoming webhook.
    # 사용자 대상 인시던트 알림과는 별개 채널이다. 없으면 알림을 건너뛴다.
    ops_webhook_url: str | None = None
    # /metrics 스크레이퍼용 정적 토큰. 없으면 엔드포인트가 404로 닫힌다 —
    # 운영 현황은 공개 정보가 아니므로 기본값은 '꺼짐'이어야 한다.
    metrics_token: str | None = None
    anthropic_api_key: str | None = None
    ai_report_model: str = "claude-opus-4-8"
    ai_report_llm_timeout_seconds: float = 30.0
    ai_report_llm_max_retries: int = 1
    ai_report_llm_max_tokens: int = 16000
    # 조사 에이전트의 LLM 판별 모델 — 기본 Haiku, 저신뢰 시 상위 모델로
    # 1회 에스컬레이션(G3 라우팅). 사용자 확정 설계(비용-정확도 곡선).
    aim_agent_model: str = "claude-haiku-4-5"
    aim_agent_escalation_model: str = "claude-sonnet-5"
    # 같은 프로젝트 조사 사이의 최소 간격 — 인시던트 연쇄로 인한 조사 폭주 방지
    aim_agent_cooldown_minutes: int = 30
    # LLM 지출 상한(USD). 쿨다운은 한 프로젝트의 폭주만 막을 뿐, 프로젝트 수가
    # 늘면 월 지출에 상한이 없다. 넘으면 조사를 멈추는 게 아니라 규칙 정책으로
    # 강등한다 — 비용 때문에 장애 진단이 통째로 사라지는 쪽이 더 나쁘다.
    # None이면 상한 없음.
    aim_agent_daily_budget_usd: float | None = None
    aim_agent_monthly_budget_usd: float | None = None
    # 모델별 백만 토큰당 단가 덮어쓰기: {"model": [input, output]}.
    # 단가는 앱보다 빨리 바뀌므로 배포 없이 고칠 수 있어야 한다.
    aim_agent_model_rates_json: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def reject_development_jwt_secret_outside_development(self) -> Self:
        """운영 환경에서 개발용/약한 서명 키로 부팅하는 것을 막는다.

        compose가 JWT_SECRET_KEY를 필수로 강제하지만 그 방어는 compose 파일에만
        있다. uvicorn을 직접 띄우거나 다른 오케스트레이터로 옮기면 기본값으로
        부팅되고, 그 키는 공개 저장소에 적혀 있어 토큰 위조가 가능해진다.
        실패는 조용하면 안 되므로 부팅 자체를 막는다.
        """
        if self.app_env in UNGUARDED_APP_ENVS:
            return self

        if self.jwt_secret_key == DEVELOPMENT_JWT_SECRET_KEY:
            raise ValueError(
                f"JWT_SECRET_KEY is still the development default in app_env="
                f"{self.app_env!r}. Set a unique secret of at least "
                f"{MIN_JWT_SECRET_KEY_LENGTH} characters."
            )

        if len(self.jwt_secret_key) < MIN_JWT_SECRET_KEY_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_KEY_LENGTH} "
                f"characters in app_env={self.app_env!r}."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
