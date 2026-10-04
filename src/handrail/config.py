"""Runtime configuration from environment variables and an optional ``.env`` file.

API keys are ``SecretStr``: they never appear in reprs, dumps or logs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when a required setting is missing, with a message a user can act on."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    planner_model: str | None = None
    jev_api_key: SecretStr | None = None
    judge_provider: Literal["jev", "llm", "none"] = "none"

    artifacts_dir: Path = Path("artifacts")
    evidence_dir: Path = Path("evidence")
    policies_dir: Path = Path("policies")
    schema_dir: Path = Path("schema")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    def require_openai_key(self) -> SecretStr:
        if self.openai_api_key is None:
            raise ConfigError("OPENAI_API_KEY is not set; add it to .env (see .env.example)")
        return self.openai_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
