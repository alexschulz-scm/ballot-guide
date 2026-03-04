"""
Session store — all SQLite operations for session lifecycle.

The orchestrator and routers call these functions for session reads/writes.
Never write raw SQL for session operations outside this file.

Cross-layer rule: orchestrator writes session state via these functions,
never with direct SQL (CLAUDE.md / Integration Review Issue 5).
"""

import json
import logging
import uuid

from apps.api.db.connection import get_db
from apps.api.db.queries import load_messages_for_session
from apps.api.db.versioning import check_data_freshness as _check_freshness
from apps.api.session.exceptions import (
    InvalidTransitionError,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)

# Token estimation: ~4 characters per token for English text.
_CHARS_PER_TOKEN = 4

# State machine: valid transitions.
_VALID_TRANSITIONS: dict[str, list[str]] = {
    "active": ["processing"],
    "processing": ["active", "error"],
    "error": ["processing"],
}


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


async def create_session(
    display_name: str | None,
    language: str,
    detected_language: str | None,
    db_path: str,
    election_id: str | None = None,
) -> str:
    """Creates a new session row. Returns the UUID v4 session_id."""
    session_id = str(uuid.uuid4())
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO sessions "
            "(id, display_name, language, detected_language, ballot_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, display_name, language, detected_language, election_id),
        )
        await db.commit()
    return session_id


async def get_session(session_id: str, db_path: str) -> dict | None:
    """
    Returns session row as dict with election_name, or None.

    JOINs elections table so election_name is populated when
    ballot_id is set (Integration Review Issue 8).
    """
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT s.*, e.name AS election_name "
            "FROM sessions s "
            "LEFT JOIN elections e ON s.ballot_id = e.id "
            "WHERE s.id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


async def update_session_status(
    session_id: str,
    status: str,
    db_path: str,
) -> None:
    """
    Updates session status after validating the transition.

    Raises SessionNotFoundError if session doesn't exist.
    Raises InvalidTransitionError if transition is illegal.
    """
    session = await get_session(session_id, db_path)
    if session is None:
        raise SessionNotFoundError(session_id)

    current = session["status"]
    allowed = _VALID_TRANSITIONS.get(current, [])
    if status not in allowed:
        raise InvalidTransitionError(current, status)

    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE sessions "
            "SET status = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (status, session_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Orchestrator stage writes
# ---------------------------------------------------------------------------


async def update_session_after_intake(
    session_id: str,
    zip_code: str,
    priorities: list[str],
    priorities_raw: str,
    display_name: str | None,
    db_path: str,
) -> None:
    """Called by orchestrator after Stage 1 (Intake) completes."""
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE sessions SET "
            "zip_code = ?, priorities_json = ?, priorities_raw = ?, "
            "display_name = COALESCE(?, display_name), "
            "updated_at = datetime('now') "
            "WHERE id = ?",
            (
                zip_code,
                json.dumps(priorities),
                priorities_raw,
                display_name,
                session_id,
            ),
        )
        await db.commit()


async def update_session_after_ballot(
    session_id: str,
    ballot_id: str,
    db_path: str,
) -> None:
    """Called by orchestrator after Stage 2 (Ballot Resolution) completes."""
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE sessions SET "
            "ballot_id = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (ballot_id, session_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------


async def save_report(
    session_id: str,
    report_json: str,
    data_version: str,
    db_path: str,
) -> None:
    """Saves completed report. Called after Stage 5 (Report Assembly)."""
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE sessions SET "
            "report_json = ?, data_version = ?, "
            "report_generated_at = datetime('now'), "
            "updated_at = datetime('now') "
            "WHERE id = ?",
            (report_json, data_version, session_id),
        )
        await db.commit()


async def get_report(session_id: str, db_path: str) -> dict | None:
    """Returns report_json parsed as dict, or None if no report exists."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT report_json FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
    if row is None or row["report_json"] is None:
        return None
    return json.loads(row["report_json"])


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------


async def save_message(
    session_id: str,
    role: str,
    content: str,
    db_path: str,
) -> None:
    """
    Saves one message. role must be 'user' or 'assistant'.

    Token count is estimated as len(content) // 4 (~4 chars/token for
    English text). Used by load_messages for context window truncation.
    """
    token_count = len(content) // _CHARS_PER_TOKEN
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO messages "
            "(session_id, role, content, token_count) "
            "VALUES (?, ?, ?, ?)",
            (session_id, role, content, token_count),
        )
        await db.commit()


async def count_messages(session_id: str, db_path: str) -> int:
    """Returns the total number of messages for a session."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
    return row[0]


async def load_messages(
    session_id: str,
    db_path: str,
    max_tokens: int = 20_000,
) -> list[dict]:
    """
    Returns message history as list of {role, content, ...} dicts.
    Delegates to queries.load_messages_for_session for truncation logic.
    """
    async with get_db(db_path) as db:
        return await load_messages_for_session(session_id, db, max_tokens)


# ---------------------------------------------------------------------------
# Data freshness
# ---------------------------------------------------------------------------


async def check_data_freshness(
    session_id: str,
    db_path: str,
) -> str:
    """
    Returns 'fresh', 'stale', 'very_stale', or 'no_report'.
    Delegates to versioning.check_data_freshness.
    """
    return await _check_freshness(session_id, db_path)
