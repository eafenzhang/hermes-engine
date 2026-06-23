"""Pydantic Settings for Hermes Engine."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from env / .env file."""

    model_config = SettingsConfigDict(
        env_prefix="HERMES_",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
    )

    # ── General ──────────────────────────────────────────────────────────
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8080

    # ── Paths ────────────────────────────────────────────────────────────
    data_dir: Path = Path.home() / ".hermes-engine"
    skills_dir: Path = data_dir / "skills"
    db_path: Path = data_dir / "hermes.db"

    # ── Provider API Keys ─────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # ── Curator ──────────────────────────────────────────────────────────
    curator_enabled: bool = True
    curator_interval_messages: int = 10
    curator_provider: str = "anthropic"
    curator_model: str = "claude-sonnet-4-20250514"

    @property
    def local_mode(self) -> bool:
        """When True, skip authentication — intended for desktop embedding."""
        return True

    # ── Security ─────────────────────────────────────────────────────────
    api_token: str = ""
    """Optional shared API token for authentication.
    When set, all requests must include ``Authorization: Bearer <token>``.
    Left empty (default) to skip authentication in local mode."""

    # Additional commands to allow in the execution whitelist.
    # The built-in base set is always present; these are supplementals.
    extra_allowed_commands: list[str] = []

    # Additional allowed base directories for file read/write tools.
    extra_allowed_dirs: list[str] = []
