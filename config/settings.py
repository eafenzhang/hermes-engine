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
    anthropic_base_url: str = ""  # custom proxy/gateway (empty = official API)
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # ── Anthropic‑compatible provider (proxy/gateway) ────────────────────
    anthropic_compat_api_key: str = ""
    anthropic_compat_base_url: str = ""  # required if key is set
    anthropic_compat_model: str = "claude-sonnet-4-20250514"  # model for connectivity check

    # ── Chinese AI Provider API Keys ──────────────────────────────────────
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    zhipu_api_key: str = ""
    qwen_api_key: str = ""
    xiaomi_api_key: str = ""
    minimax_api_key: str = ""

    # ── OpenAI-compatible base URLs ───────────────────────────────────────
    # Each provider has a sensible default except Xiaomi (unknown endpoint).
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    xiaomi_base_url: str = ""
    minimax_base_url: str = "https://api.minimax.chat/v1"

    # ── Curator ──────────────────────────────────────────────────────────
    curator_enabled: bool = True
    curator_interval_messages: int = 10
    curator_provider: str = "anthropic"
    curator_model: str = "claude-sonnet-4-20250514"

    # ── Model cache ──────────────────────────────────────────────────────
    model_cache_ttl: float = 300.0

    # ── Context compression ──────────────────────────────────────────────
    context_compression_enabled: bool = True
    context_max_chars: int = 60000
    context_keep_last_messages: int = 6

    # ── Skill auto-generation ────────────────────────────────────────────
    skill_auto_create_enabled: bool = True
    skill_auto_create_min_tool_calls: int = 5

    # ── Sub-agent delegation ─────────────────────────────────────────────
    subagent_timeout: float = 300.0
    subagent_max_concurrent: int = 3

    # ── Terminal backends ────────────────────────────────────────────────
    terminal_backend: str = "local"  # "local" | "docker" | "ssh"
    docker_image: str = "python:3.12-slim"
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_key_path: str = ""
    ssh_port: int = 22

    # ── Browser automation ───────────────────────────────────────────────
    browser_enabled: bool = True

    # ── User context files ───────────────────────────────────────────────
    user_context_enabled: bool = True

    # ── Curator grading ──────────────────────────────────────────────────
    curator_grading_enabled: bool = True
    curator_stale_days: int = 30
    curator_archive_days: int = 90

    # ── Cron scheduler ───────────────────────────────────────────────────
    cron_enabled: bool = True

    # ── Gateway / webhook ────────────────────────────────────────────────
    gateway_enabled: bool = True

    # ── Plugin system ────────────────────────────────────────────────────
    plugins_enabled: bool = True
    plugins_dirs: list[str] = []

    # ── Trajectory export ────────────────────────────────────────────────
    trajectories_enabled: bool = True

    # ── Stateful sessions ────────────────────────────────────────────────
    session_enabled: bool = True
    session_search_max: int = 3
    cron_nl_enabled: bool = True

    @property
    def local_mode(self) -> bool:
        """Whether authentication is skipped (desktop / local embedding).

        Local mode is active when *no* API token is configured. Once an
        operator sets ``HERMES_API_TOKEN``, ``local_mode`` flips to ``False``
        and every request (except public health checks) must authenticate —
        matching the behaviour enforced by ``AuthMiddleware``.
        """
        return not bool(self.api_token)

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

    # MCP server connection timeout in seconds.
    mcp_timeout: float = 30.0

    # CORS — comma-separated origins (e.g. "http://localhost:3000,https://app.com")
    cors_origins: list[str] = ["*"]
