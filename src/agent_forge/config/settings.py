"""Application settings with pydantic-settings."""

import os
from pathlib import Path
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — loaded via custom init to support both OPENAI_API_KEY and AGENT_FORGE_OPENAI_API_KEY
    openai_api_key: str = ""

    def model_post_init(self, __context) -> None:
        """Fall back to OPENAI_API_KEY if prefixed version not set."""
        if not self.openai_api_key:
            from dotenv import dotenv_values
            env_vals = dotenv_values(".env")
            key = os.environ.get("OPENAI_API_KEY") or env_vals.get("OPENAI_API_KEY", "")
            if key:
                object.__setattr__(self, "openai_api_key", key)
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 4096

    # GitHub
    github_token: str = ""
    prefer_gh_cli: bool = True

    # Agent behavior
    max_reflexion_iterations: int = 3
    test_timeout_seconds: int = 300
    max_tests_per_run: int = 50

    # Paths
    work_dir: Path = Path.home() / ".agent-forge" / "work"
    reports_dir: Path = Path.home() / ".agent-forge" / "reports"

    def ensure_dirs(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
