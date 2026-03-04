"""
Tests for GET /health endpoint.
"""

import json

import pytest


@pytest.mark.asyncio
async def test_health_returns_200_when_db_ok(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_503_when_db_inaccessible(async_client, monkeypatch):
    """Simulate DB failure by pointing settings.DB_PATH to an invalid path."""
    from apps.api.config import settings

    original = settings.DB_PATH
    settings.DB_PATH = "/nonexistent/dir/impossible.db"
    try:
        response = await async_client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"] == "error"
    finally:
        settings.DB_PATH = original


@pytest.mark.asyncio
async def test_health_includes_version(async_client):
    response = await async_client.get("/health")
    data = response.json()
    assert "version" in data
    assert data["version"] == "1.0.0"
    assert "timestamp" in data
