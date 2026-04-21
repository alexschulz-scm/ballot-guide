"""
Tests for security hardening: security headers, rate limit handler,
config validation, elections router, and input validators.
"""

import os

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_CIVIC_API_KEY", "test-key")
os.environ.setdefault("NEWSAPI_KEY", "test-key")
os.environ.setdefault("OPENFEC_API_KEY", "test-key")
os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("MOCK_EXTERNAL_APIS", "true")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from apps.api.config import settings
from apps.api.db.connection import get_db, run_migrations
from apps.api.main import app
from apps.api.models import CreateSessionRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test_sec.db")
    await run_migrations(path)
    original = settings.DB_PATH
    settings.DB_PATH = path
    yield path
    settings.DB_PATH = original


@pytest_asyncio.fixture
async def client(db_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Security headers (#11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_on_health(client):
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers.get("permissions-policy", "")
    assert "default-src 'self'" in resp.headers.get("content-security-policy", "")


# ---------------------------------------------------------------------------
# Elections router (#10 in coverage)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_elections_returns_200(client):
    """Elections route returns 200 with list (seeded by migrations)."""
    resp = await client.get("/api/v1/elections")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Migrations seed FL-2022-GEN and FL-2024-GEN
    assert len(data) >= 2
    assert all("id" in item for item in data)


@pytest.mark.asyncio
async def test_get_elections_ordered_by_date_desc(client):
    """Elections are returned newest first."""
    resp = await client.get("/api/v1/elections")
    data = resp.json()
    dates = [item["election_date"] for item in data]
    assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# Session ID UUID validation (#15)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_session_id_format(client):
    """Non-UUID session_id returns 404 without hitting DB."""
    resp = await client.get("/api/v1/session/not-a-uuid")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_session_id_on_report(client):
    resp = await client.get("/api/v1/session/bad-id/report")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_session_id_on_message(client):
    resp = await client.post(
        "/api/v1/session/bad-id/message",
        json={"content": "hello"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session enumeration fix (#13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_not_found_no_id_leak(client):
    """Error message must not echo the session_id back."""
    resp = await client.get("/api/v1/session/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    body = resp.json()
    assert "00000000" not in body["message"]
    assert body["message"] == "Session not found."


# ---------------------------------------------------------------------------
# Error response has no detail (#8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_response_no_detail(client):
    """500 errors must not expose internal exception details."""
    resp = await client.get("/api/v1/session/00000000-0000-0000-0000-000000000000")
    body = resp.json()
    assert "detail" not in body or body.get("detail") is None


# ---------------------------------------------------------------------------
# Input validation (#14)
# ---------------------------------------------------------------------------


class TestCreateSessionRequest:
    def test_valid_election_id(self):
        req = CreateSessionRequest(election_id="FL-2026-GEN")
        assert req.election_id == "FL-2026-GEN"

    def test_invalid_election_id(self):
        with pytest.raises(ValidationError, match="election_id"):
            CreateSessionRequest(election_id="invalid-format")

    def test_none_election_id(self):
        req = CreateSessionRequest(election_id=None)
        assert req.election_id is None

    def test_display_name_too_long(self):
        with pytest.raises(ValidationError, match="50 characters"):
            CreateSessionRequest(display_name="x" * 51)

    def test_display_name_valid(self):
        req = CreateSessionRequest(display_name="Alex")
        assert req.display_name == "Alex"


# ---------------------------------------------------------------------------
# Config validate_required (#10 logging fix)
# ---------------------------------------------------------------------------


def test_config_validate_required_logs_loaded(caplog):
    """Secrets must be logged as <loaded>, never with prefix."""
    import logging
    with caplog.at_level(logging.INFO, logger="apps.api.config"):
        settings.validate_required()
    for key in ["GEMINI_API_KEY", "GOOGLE_CIVIC_API_KEY", "NEWSAPI_KEY", "OPENFEC_API_KEY"]:
        assert any(f"{key} = <loaded>" in rec.message for rec in caplog.records), (
            f"{key} not logged as <loaded>"
        )
    # Ensure no secret prefixes logged
    assert not any("sk-" in rec.message for rec in caplog.records)
    assert not any("test-key" in rec.message for rec in caplog.records)
