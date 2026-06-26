"""Shared test fixtures — ephemeral app with temporary SQLite database."""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

# Suppress Starlette TestClient deprecation warning — httpx migration
# requires broader async refactor (tracked for future iteration).
warnings.filterwarnings("ignore", message=".*starlette.testclient.*")
warnings.filterwarnings("ignore", message=".*httpx.*starlette.*")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from typing import Generator

from config.settings import Settings
from main import create_app


@pytest.fixture(autouse=True)
def _clean_singletons():
    """Reset module-level singletons between tests to prevent state leaks."""
    yield
    # Clear MCP bridge singleton
    try:
        import asyncio
        from mcp.bridge import bridge
        bridge._servers.clear()
        bridge._pending_closes.clear()
    except Exception:
        pass
    # Clear provider registry
    try:
        from provider.registry import registry
        for name in list(registry._providers.keys()):
            registry.remove(name)
    except Exception:
        pass
    # Clear SQLite connection paths
    try:
        from shared.sqlite_base import SQLiteBase
        SQLiteBase._connection_paths.clear()
    except Exception:
        pass


@pytest.fixture
def tmp_settings() -> Settings:
    """Create Settings with temporary data directory (no API keys)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="hermes_test_"))
    return Settings(
        data_dir=tmpdir,
        skills_dir=tmpdir / "skills",
        db_path=tmpdir / "test.db",
        debug=False,
        anthropic_api_key="",
        openai_api_key="",
        gemini_api_key="",
    )


@pytest.fixture
def app(tmp_settings: Settings):
    """Create a test FastAPI app instance."""
    return create_app(tmp_settings)


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Sync TestClient — handles lifespan events and WebSocket connections."""
    with TestClient(app) as tc:
        yield tc
