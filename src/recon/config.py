"""Application settings, loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,  # `PROVIDER_API_KEY=` in .env means "unset", not ""
    )

    # --- Database ---
    database_url: str = "sqlite:///./recon.db"
    sql_echo: bool = False

    # --- Logging ---
    log_level: LogLevel = "INFO"

    # --- Secrets (SecretStr hides the value in repr/logs; use .get_secret_value()) ---
    webhook_signing_secret: SecretStr | None = None
    webhook_timestamp_tolerance_seconds: int = Field(default=300, gt=0)
    provider_api_key: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; use as a FastAPI dependency or call directly."""
    return Settings()