"""Shared test fixtures — ephemeral app with temporary SQLite database."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

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
def client(app) -> TestClient:
    """Sync TestClient — handles lifespan events and WebSocket connections."""
    with TestClient(app) as tc:
        yield tc
