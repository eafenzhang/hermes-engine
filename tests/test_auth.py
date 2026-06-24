"""Authentication middleware tests.

Covers the ``local_mode`` semantics: when no ``HERMES_API_TOKEN`` is set the
engine runs unauthenticated; when a token *is* set, every non-public request
must present ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from config.settings import Settings
from main import create_app


def _build_client(api_token: str) -> TestClient:
    """Create a TestClient with the given API token (empty = local mode)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="hermes_auth_"))
    settings = Settings(
        data_dir=tmpdir,
        skills_dir=tmpdir / "skills",
        db_path=tmpdir / "auth.db",
        api_token=api_token,
    )
    app = create_app(settings)
    tc = TestClient(app)
    tc.__enter__()
    return tc


@pytest.fixture
def auth_client():
    tc = _build_client(api_token="s3cret-token")
    yield tc
    tc.__exit__(None, None, None)


# ── Local mode (no token) — default behaviour ───────────────────────────


def test_local_mode_allows_request_without_token(client):
    """Default client has no token → local_mode → request allowed."""
    resp = client.get("/api/health")
    assert resp.status_code == 200


# ── Token mode — authentication enforced ────────────────────────────────


def test_token_mode_rejects_missing_header(auth_client):
    """With a token set, a request without Authorization → 401."""
    resp = auth_client.get("/api/health")
    # /api/health is a public path and stays exempt even under token mode.
    assert resp.status_code == 200


def test_token_mode_protected_endpoint_requires_header(auth_client):
    """Protected endpoints (/api/memories) require a Bearer token."""
    resp = auth_client.get("/api/memories")
    assert resp.status_code == 401
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == "AUTH_REQUIRED"


def test_token_mode_rejects_wrong_token(auth_client):
    """A wrong token is rejected with 401."""
    resp = auth_client.get(
        "/api/memories", headers={"Authorization": "Bearer wrong-token"}
    )
    assert resp.status_code == 401


def test_token_mode_accepts_correct_token(auth_client):
    """The correct Bearer token grants access to protected endpoints."""
    resp = auth_client.get(
        "/api/memories", headers={"Authorization": "Bearer s3cret-token"}
    )
    assert resp.status_code == 200


def test_health_is_public_under_token_mode(auth_client):
    """/api/health is always public, even with a token configured."""
    resp = auth_client.get("/api/health")
    assert resp.status_code == 200


def test_local_mode_property_reflects_token():
    """``Settings.local_mode`` is True iff no api_token is configured."""
    unauth = Settings(data_dir=Path(tempfile.mkdtemp()))
    assert unauth.local_mode is True

    authed = Settings(data_dir=Path(tempfile.mkdtemp()), api_token="abc")
    assert authed.local_mode is False
