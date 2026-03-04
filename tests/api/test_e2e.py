"""
End-to-end API test — full session lifecycle with mock orchestrator.

Covers AC-07 (progressive item_analyzed), AC-09 (valid JSON), CORS (DoD).
Uses mock_orchestrator_with_items fixture for the full event sequence.
"""

import json

import pytest

from apps.api.session.store import create_session, save_report


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
async def test_full_session_lifecycle(
    async_client, db_path, mock_orchestrator_with_items
):
    """
    Full flow: create session → send message → stream events → get report
    → verify session metadata. Covers AC-07, AC-09.
    """
    # 1. POST /session → get session_id
    create_resp = await async_client.post("/api/v1/session")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    # 2. POST /session/{id}/message → consume SSE stream
    msg_resp = await async_client.post(
        f"/api/v1/session/{session_id}/message",
        json={"content": "I live in 33101 and care about housing"},
    )
    assert msg_resp.status_code == 200
    assert "text/event-stream" in msg_resp.headers["content-type"]

    # 3. Parse events
    events = _parse_sse_events(msg_resp.text)
    event_types = [e["type"] for e in events]

    # AC-09: All event data payloads parse as valid JSON (implicit — parse above)
    # If any payload was invalid JSON, json.loads in _parse_sse_events would throw
    assert len(events) > 0

    # AC-07: item_analyzed events arrive before report_complete
    assert "item_analyzed" in event_types
    assert "report_complete" in event_types
    item_idx = event_types.index("item_analyzed")
    report_idx = event_types.index("report_complete")
    assert item_idx < report_idx

    # Verify full event sequence
    assert event_types[0] == "intake_complete"
    assert "ballot_found" in event_types
    assert "ranking_complete" in event_types
    assert event_types[-1] == "done"

    # 4. GET /session/{id}/report → report returned
    # The mock orchestrator doesn't actually persist the report via the real
    # runner path (save_report), so we save it manually for this e2e test.
    report_event = [e for e in events if e["type"] == "report_complete"][0]
    report_json = json.dumps(report_event["data"]["report"])
    await save_report(session_id, report_json, "e2e-test-version", db_path)

    report_resp = await async_client.get(
        f"/api/v1/session/{session_id}/report"
    )
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["session_id"] == session_id
    assert report_data["report"] is not None

    # 5. GET /session/{id} → metadata shows report
    meta_resp = await async_client.get(f"/api/v1/session/{session_id}")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["has_report"] is True
    assert meta["message_count"] >= 2  # user msg + assistant msg


@pytest.mark.asyncio
async def test_cors_allows_configured_origin(async_client, db_path):
    """CORS DoD: requests from configured origin get CORS headers."""
    response = await async_client.options(
        "/api/v1/session",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_blocks_unconfigured_origin(async_client, db_path):
    """CORS DoD: requests from unconfigured origin do NOT get CORS headers."""
    response = await async_client.options(
        "/api/v1/session",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # CORSMiddleware should not include the origin in the response
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "http://evil.com"
