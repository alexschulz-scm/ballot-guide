"""
Tests for apps/api/session/store.py — session lifecycle operations.

All tests use file-based temp SQLite (not :memory:) because each store
function opens its own connection via get_db(db_path).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from apps.api.db.connection import get_db
from apps.api.session.exceptions import (
    InvalidTransitionError,
    SessionNotFoundError,
)
from apps.api.session.store import (
    check_data_freshness,
    create_session,
    get_report,
    get_session,
    load_messages,
    save_message,
    save_report,
    update_session_after_ballot,
    update_session_after_intake,
    update_session_status,
)


# ─────────────────────────────────────────────
# Session creation
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session_returns_uuid(db_path):
    sid = await create_session("Maria", "en", "es", db_path)
    # Validate UUID v4 format
    parsed = uuid.UUID(sid, version=4)
    assert str(parsed) == sid


@pytest.mark.asyncio
async def test_create_session_writes_to_db(db_path):
    sid = await create_session("Alex", "en", "en-US", db_path)
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ?", (sid,)
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row["display_name"] == "Alex"
    assert row["language"] == "en"
    assert row["detected_language"] == "en-US"
    assert row["status"] == "active"


# ─────────────────────────────────────────────
# Session retrieval
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_session_returns_none_for_unknown_id(db_path):
    result = await get_session("nonexistent-id", db_path)
    assert result is None


@pytest.mark.asyncio
async def test_get_session_returns_election_name_via_join(db_path):
    """
    Gate test — Integration Review Issue 8.
    When ballot_id is set, election_name comes from elections.name via JOIN.
    """
    # Insert an election
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO elections (id, state, election_type, election_date, name) "
            "VALUES (?, ?, ?, ?, ?)",
            ("FL-2026-GEN", "FL", "general", "2026-11-03", "2026 Florida General Election"),
        )
        await db.commit()

    sid = await create_session(None, "en", None, db_path)
    await update_session_after_ballot(sid, "FL-2026-GEN", db_path)

    session = await get_session(sid, db_path)
    assert session is not None
    assert session["election_name"] == "2026 Florida General Election"


@pytest.mark.asyncio
async def test_get_session_returns_none_election_name_when_no_ballot(db_path):
    """When ballot_id is NULL, election_name should be None."""
    sid = await create_session(None, "en", None, db_path)
    session = await get_session(sid, db_path)
    assert session is not None
    assert session["election_name"] is None


# ─────────────────────────────────────────────
# Status transitions (state machine)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_session_status_valid_transition(db_path):
    sid = await create_session(None, "en", None, db_path)
    # active → processing
    await update_session_status(sid, "processing", db_path)
    session = await get_session(sid, db_path)
    assert session["status"] == "processing"

    # processing → active
    await update_session_status(sid, "active", db_path)
    session = await get_session(sid, db_path)
    assert session["status"] == "active"


@pytest.mark.asyncio
async def test_update_session_status_invalid_transition_raises(db_path):
    """active → error is not a valid transition."""
    sid = await create_session(None, "en", None, db_path)
    with pytest.raises(InvalidTransitionError) as exc_info:
        await update_session_status(sid, "error", db_path)
    assert exc_info.value.current_status == "active"
    assert exc_info.value.requested_status == "error"


@pytest.mark.asyncio
async def test_processing_to_processing_raises_invalid_transition(db_path):
    """
    Gate test — concurrent run protection.
    processing → processing must be rejected.
    """
    sid = await create_session(None, "en", None, db_path)
    await update_session_status(sid, "processing", db_path)
    with pytest.raises(InvalidTransitionError):
        await update_session_status(sid, "processing", db_path)


@pytest.mark.asyncio
async def test_update_session_status_error_to_processing(db_path):
    """error → processing is valid (user can retry)."""
    sid = await create_session(None, "en", None, db_path)
    await update_session_status(sid, "processing", db_path)
    await update_session_status(sid, "error", db_path)
    await update_session_status(sid, "processing", db_path)
    session = await get_session(sid, db_path)
    assert session["status"] == "processing"


@pytest.mark.asyncio
async def test_update_session_status_not_found_raises(db_path):
    with pytest.raises(SessionNotFoundError):
        await update_session_status("no-such-session", "processing", db_path)


# ─────────────────────────────────────────────
# Orchestrator stage writes
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_session_after_intake_persists_fields(db_path):
    sid = await create_session("Original Name", "en", None, db_path)
    await update_session_after_intake(
        sid, "33101", ["housing", "education"], "housing and schools", "Maria", db_path
    )
    session = await get_session(sid, db_path)
    assert session["zip_code"] == "33101"
    assert json.loads(session["priorities_json"]) == ["housing", "education"]
    assert session["priorities_raw"] == "housing and schools"
    assert session["display_name"] == "Maria"


@pytest.mark.asyncio
async def test_update_session_after_intake_preserves_display_name(db_path):
    """If intake returns None for display_name, keep the original."""
    sid = await create_session("Original", "en", None, db_path)
    await update_session_after_intake(
        sid, "33101", ["housing"], "housing", None, db_path
    )
    session = await get_session(sid, db_path)
    assert session["display_name"] == "Original"


@pytest.mark.asyncio
async def test_update_session_after_ballot_sets_ballot_id(db_path):
    # Need a valid election for the FK
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO elections (id, state, election_type, election_date, name) "
            "VALUES (?, ?, ?, ?, ?)",
            ("FL-2026-GEN", "FL", "general", "2026-11-03", "2026 FL General"),
        )
        await db.commit()

    sid = await create_session(None, "en", None, db_path)
    await update_session_after_ballot(sid, "FL-2026-GEN", db_path)
    session = await get_session(sid, db_path)
    assert session["ballot_id"] == "FL-2026-GEN"


# ─────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_load_messages_round_trip(db_path):
    sid = await create_session(None, "en", None, db_path)
    await save_message(sid, "user", "Hello, I live in 33101", db_path)
    await save_message(sid, "assistant", "I found your ballot.", db_path)
    await save_message(sid, "user", "What about housing?", db_path)

    messages = await load_messages(sid, db_path)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello, I live in 33101"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


@pytest.mark.asyncio
async def test_load_messages_never_drops_first_message(db_path):
    sid = await create_session(None, "en", None, db_path)

    # First message is long — set up so budget forces truncation
    first_msg = "I live at 123 Main St, Miami FL 33101 and care about housing"
    await save_message(sid, "user", first_msg, db_path)

    # Add several more messages
    for i in range(10):
        await save_message(sid, "assistant", f"Response {i} " * 50, db_path)
        await save_message(sid, "user", f"Follow-up {i} " * 50, db_path)

    # Load with tight budget — should still include first message
    messages = await load_messages(sid, db_path, max_tokens=100)
    assert len(messages) >= 1
    assert messages[0]["content"] == first_msg


# ─────────────────────────────────────────────
# Report persistence
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_report_persists_json(db_path):
    sid = await create_session(None, "en", None, db_path)
    report = {"session_id": sid, "items": [{"title": "Amendment 1"}]}
    await save_report(sid, json.dumps(report), "abcdef1234567890", db_path)

    session = await get_session(sid, db_path)
    assert session["report_json"] is not None
    assert session["data_version"] == "abcdef1234567890"
    assert session["report_generated_at"] is not None


@pytest.mark.asyncio
async def test_get_report_returns_none_when_missing(db_path):
    sid = await create_session(None, "en", None, db_path)
    result = await get_report(sid, db_path)
    assert result is None


@pytest.mark.asyncio
async def test_get_report_returns_parsed_dict(db_path):
    sid = await create_session(None, "en", None, db_path)
    report = {"session_id": sid, "items": []}
    await save_report(sid, json.dumps(report), "abc123", db_path)
    result = await get_report(sid, db_path)
    assert isinstance(result, dict)
    assert result["session_id"] == sid


# ─────────────────────────────────────────────
# Data freshness
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_data_freshness_returns_fresh_for_new_report(db_path):
    """Delegates to versioning.check_data_freshness. Seed data for a real check."""
    from scripts.seed_historical import seed_database
    from apps.api.db.versioning import _compute_current_data_version

    await seed_database(db_path)
    current_version = await _compute_current_data_version("FL-2022-GEN", db_path)

    sid = await create_session(None, "en", None, db_path)
    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()

    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE sessions SET "
            "report_json = ?, data_version = ?, report_generated_at = ?, "
            "ballot_id = ? WHERE id = ?",
            ('{"ok":1}', current_version, recent_ts, "FL-2022-GEN", sid),
        )
        await db.commit()

    result = await check_data_freshness(sid, db_path)
    assert result == "fresh"


# ─────────────────────────────────────────────
# Infrastructure (migration, WAL)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_migration_runs_idempotently(db_path):
    """Running migrations twice on the same DB produces no error."""
    from apps.api.db.connection import run_migrations
    applied = await run_migrations(db_path)
    assert applied == []  # All already applied from conftest


@pytest.mark.asyncio
async def test_wal_mode_enabled_after_connection(db_path):
    async with get_db(db_path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
    assert row[0] == "wal"
