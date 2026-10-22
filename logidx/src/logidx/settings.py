"""Runtime settings. Every secret comes from the environment (or a .env file), never from the database."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default=f"sqlite:///{PROJECT_ROOT / 'data' / 'logidx.db'}", alias="LOGIDX_DATABASE_URL")
    config_dir: Path = Field(default=PROJECT_ROOT / "config", alias="LOGIDX_CONFIG_DIR")
    data_dir: Path = Field(default=PROJECT_ROOT / "data", alias="LOGIDX_DATA_DIR")
    timezone: str = Field(default="Australia/Melbourne", alias="LOGIDX_TIMEZONE")

    secret_key: SecretStr = Field(default=SecretStr(""), alias="LOGIDX_SECRET_KEY")
    cookie_secure: bool = Field(default=True, alias="LOGIDX_COOKIE_SECURE")
    enable_scheduler: bool = Field(default=True, alias="LOGIDX_ENABLE_SCHEDULER")

    contact_email: str = Field(default="", alias="LOGIDX_CONTACT_EMAIL")
    http_timeout_seconds: float = Field(default=30.0, alias="LOGIDX_HTTP_TIMEOUT")
    http_min_interval_seconds: float = Field(default=1.0, alias="LOGIDX_HTTP_MIN_INTERVAL")

    # AI provider (xAI Grok by default; the provider interface allows others).
    ai_provider: str = Field(default="grok", alias="LOGIDX_AI_PROVIDER")
    xai_api_key: SecretStr = Field(default=SecretStr(""), alias="XAI_API_KEY")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
    xai_model: str = Field(default="grok-4", alias="XAI_MODEL")
    ai_price_input_per_mtok: float = Field(default=3.0, alias="LOGIDX_AI_PRICE_INPUT_PER_MTOK")
    ai_price_output_per_mtok: float = Field(default=15.0, alias="LOGIDX_AI_PRICE_OUTPUT_PER_MTOK")
    ai_daily_budget_usd: float = Field(default=5.0, alias="LOGIDX_AI_DAILY_BUDGET_USD")
    ai_max_assessments_per_run: int = Field(default=40, alias="LOGIDX_AI_MAX_PER_RUN")

    # Sources
    adzuna_app_id: SecretStr = Field(default=SecretStr(""), alias="ADZUNA_APP_ID")
    adzuna_app_key: SecretStr = Field(default=SecretStr(""), alias="ADZUNA_APP_KEY")
    google_cse_key: SecretStr = Field(default=SecretStr(""), alias="GOOGLE_CSE_KEY")
    google_cse_cx: str = Field(default="", alias="GOOGLE_CSE_CX")

    # Notifications
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: SecretStr = Field(default=SecretStr(""), alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    report_recipient: str = Field(default="", alias="LOGIDX_REPORT_RECIPIENT")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def user_agent(self) -> str:
        contact = f"; contact {self.contact_email}" if self.contact_email else ""
        return f"LogiDxExecutiveSearch/0.1 (personal job-search tool{contact})"

    def secret_values(self) -> list[str]:
        """Every configured secret, for log redaction."""
        secrets = [
            self.secret_key,
            self.xai_api_key,
            self.adzuna_app_id,
            self.adzuna_app_key,
            self.google_cse_key,
            self.smtp_password,
        ]
        return [s.get_secret_value() for s in secrets if s.get_secret_value()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
