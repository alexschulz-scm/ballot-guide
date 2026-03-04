"""
Tests for POST /api/v1/session/{id}/message (SSE streaming).

Uses mock_orchestrator and mock_orchestrator_error fixtures from conftest.
"""

import json

import pytest

from apps.api.session.store import create_session, update_session_status


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into a list of event dicts (event_type + data)."""
    events = []
    current_type = None
    for line in text.split("\n"):
        if line.startswith("event: "):
            current_type = line[7:].strip()
        elif line.startswith("data: "):
            data = json.loads(line[6:].strip())
            events.append({"type": current_type, "data": data})
            current_type = None
    return events


@pytest.mark.asyncio
async def test_send_message_returns_event_stream_content_type(
    async_client, db_path, mock_orchestrator
):
    sid = await create_session(None, "en", None, db_path)
    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "I live in 33101"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_send_message_has_x_accel_buffering_header(
    async_client, db_path, mock_orchestrator
):
    """Gate test — X-Accel-Buffering: no is critical for SSE through nginx."""
    sid = await create_session(None, "en", None, db_path)
    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "I live in 33101"},
    )
    assert response.headers.get("x-accel-buffering") == "no"


@pytest.mark.asyncio
async def test_send_message_stream_ends_with_done_event(
    async_client, db_path, mock_orchestrator
):
    """Gate test — done event is always the last SSE event."""
    sid = await create_session(None, "en", None, db_path)
    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "I live in 33101"},
    )
    events = _parse_sse_events(response.text)
    assert len(events) > 0
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["event_type"] == "done"
    assert "timestamp" in events[-1]["data"]


@pytest.mark.asyncio
async def test_send_message_error_stream_still_ends_with_done(
    async_client, db_path, mock_orchestrator_error
):
    """Gate test — done fires even when orchestrator raises an exception."""
    sid = await create_session(None, "en", None, db_path)
    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "I live in 33101"},
    )
    events = _parse_sse_events(response.text)
    assert len(events) >= 2
    # Should have an error event followed by done
    event_types = [e["type"] for e in events]
    assert "error" in event_types
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_send_message_empty_content_returns_422(async_client, db_path):
    sid = await create_session(None, "en", None, db_path)
    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_message_too_long_returns_422(async_client, db_path):
    sid = await create_session(None, "en", None, db_path)
    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "x" * 501},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_message_processing_session_returns_409(
    async_client, db_path, mock_orchestrator
):
    """Gate test — SESSION_BUSY when session is already processing."""
    sid = await create_session(None, "en", None, db_path)
    await update_session_status(sid, "processing", db_path)

    response = await async_client.post(
        f"/api/v1/session/{sid}/message",
        json={"content": "Hello"},
    )
    assert response.status_code == 409
    data = response.json()
    assert data["error_code"] == "SESSION_BUSY"


@pytest.mark.asyncio
async def test_send_message_unknown_session_returns_404(async_client):
    response = await async_client.post(
        "/api/v1/session/nonexistent-id/message",
        json={"content": "Hello"},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "SESSION_NOT_FOUND"
