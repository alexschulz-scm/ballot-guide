"""
Tests for POST /api/v1/session and GET /api/v1/session/{id}.
"""

import json

import pytest

from apps.api.session.store import create_session, save_message


@pytest.mark.asyncio
async def test_create_session_returns_201(async_client):
    response = await async_client.post("/api/v1/session")
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "active"
    assert data["language"] == "en"


@pytest.mark.asyncio
async def test_create_session_with_display_name(async_client):
    response = await async_client.post(
        "/api/v1/session",
        json={"display_name": "Maria"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] == "Maria"


@pytest.mark.asyncio
async def test_create_session_with_no_body_defaults(async_client):
    response = await async_client.post("/api/v1/session")
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] is None
    assert data["language"] == "en"


@pytest.mark.asyncio
async def test_create_session_invalid_language_returns_422(async_client):
    response = await async_client.post(
        "/api/v1/session",
        json={"language": "es"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_session_metadata_returns_200(async_client, db_path):
    # Create a session first
    create_resp = await async_client.post("/api/v1/session")
    sid = create_resp.json()["session_id"]

    response = await async_client.get(f"/api/v1/session/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == sid
    assert data["status"] == "active"
    assert data["priorities"] == []
    assert data["has_report"] is False
    assert data["message_count"] == 0


@pytest.mark.asyncio
async def test_get_session_unknown_id_returns_404_with_error_code(async_client):
    response = await async_client.get("/api/v1/session/nonexistent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_session_includes_message_count(async_client, db_path):
    create_resp = await async_client.post("/api/v1/session")
    sid = create_resp.json()["session_id"]

    await save_message(sid, "user", "Hello", db_path)
    await save_message(sid, "assistant", "Hi there", db_path)

    response = await async_client.get(f"/api/v1/session/{sid}")
    data = response.json()
    assert data["message_count"] == 2
