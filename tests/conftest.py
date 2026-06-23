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
