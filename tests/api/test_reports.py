"""
Tests for GET /api/v1/session/{id}/report.
"""

import json

import pytest

from apps.api.db.connection import get_db
from apps.api.session.store import (
    create_session,
    save_report,
    update_session_status,
)


@pytest.mark.asyncio
async def test_get_report_returns_200_with_report(async_client, db_path):
    sid = await create_session(None, "en", None, db_path)
    report = {"session_id": sid, "items": [{"title": "Amendment 1"}]}
    await save_report(sid, json.dumps(report), "abcdef1234567890", db_path)

    response = await async_client.get(f"/api/v1/session/{sid}/report")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == sid
    assert data["report"]["session_id"] == sid
    assert "generated_at" in data
    assert "data_freshness" in data


@pytest.mark.asyncio
async def test_get_report_no_report_returns_404_report_not_ready(async_client, db_path):
    sid = await create_session(None, "en", None, db_path)

    response = await async_client.get(f"/api/v1/session/{sid}/report")
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "REPORT_NOT_READY"


@pytest.mark.asyncio
async def test_get_report_processing_returns_202(async_client, db_path):
    sid = await create_session(None, "en", None, db_path)
    await update_session_status(sid, "processing", db_path)

    response = await async_client.get(f"/api/v1/session/{sid}/report")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "processing"


@pytest.mark.asyncio
async def test_get_report_unknown_session_returns_404(async_client):
    response = await async_client.get("/api/v1/session/nonexistent-id/report")
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_report_stale_data_returns_stale_freshness(async_client, db_path):
    """AC-11: Report with mismatched data_version returns 'stale'."""
    from datetime import datetime, timedelta, timezone

    sid = await create_session(None, "en", None, db_path)
    report = {"session_id": sid, "items": []}
    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()

    # Save report with a data_version that won't match current data
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO elections (id, state, election_type, "
            "election_date, name) VALUES (?, ?, ?, ?, ?)",
            ("FL-STALE", "FL", "general", "2026-11-03", "Stale Test"),
        )
        await db.execute(
            "UPDATE sessions SET "
            "report_json = ?, data_version = ?, "
            "report_generated_at = ?, ballot_id = ? WHERE id = ?",
            (
                json.dumps(report),
                "old-version-does-not-match",
                recent_ts,
                "FL-STALE",
                sid,
            ),
        )
        await db.commit()

    response = await async_client.get(f"/api/v1/session/{sid}/report")
    assert response.status_code == 200
    data = response.json()
    assert data["data_freshness"] == "stale"


@pytest.mark.asyncio
async def test_get_report_includes_freshness(async_client, db_path):
    """Report with matching data_version should be 'fresh'."""
    from scripts.seed_historical import seed_database
    from apps.api.db.versioning import _compute_current_data_version
    from datetime import datetime, timedelta, timezone

    await seed_database(db_path)
    current_version = await _compute_current_data_version("FL-2022-GEN", db_path)

    sid = await create_session(None, "en", None, db_path)
    report = {"session_id": sid, "items": []}
    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE sessions SET "
            "report_json = ?, data_version = ?, report_generated_at = ?, "
            "ballot_id = ? WHERE id = ?",
            (json.dumps(report), current_version, recent_ts, "FL-2022-GEN", sid),
        )
        await db.commit()

    response = await async_client.get(f"/api/v1/session/{sid}/report")
    assert response.status_code == 200
    data = response.json()
    assert data["data_freshness"] == "fresh"
