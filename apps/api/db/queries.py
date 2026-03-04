"""
Canonical query functions for the ballot-guide database.

All other components (routers, orchestrator stages, MCP tools) must call
these functions — never write ad-hoc SQL elsewhere.
"""
import json
from datetime import datetime, timezone

import aiosqlite

# TTL for cache entries in seconds. Defined here, not inline in callers.
DEFAULT_CACHE_TTL_SECONDS = 3600  # 1 hour


async def load_messages_for_session(
    session_id: str,
    db: aiosqlite.Connection,
    max_tokens: int = 20_000,
) -> list[dict]:
    """
    Returns message history for a session, oldest first.
    Drops oldest messages (never the first) to stay within max_tokens.
    """
    cursor = await db.execute(
        "SELECT id, role, content, token_count, created_at "
        "FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    rows = await cursor.fetchall()
    messages = [dict(row) for row in rows]

    if not messages:
        return messages

    total = sum(m["token_count"] or 0 for m in messages)
    if total <= max_tokens:
        return messages

    # Drop from index 1 upward; never drop the first message (index 0).
    while len(messages) > 1 and total > max_tokens:
        removed = messages.pop(1)
        total -= removed["token_count"] or 0

    return messages


async def get_cached_data(
    cache_key: str,
    db: aiosqlite.Connection,
) -> dict | None:
    """
    Returns parsed dict if cache hit (entry exists and not expired), None otherwise.
    """
    cursor = await db.execute(
        "SELECT data_json FROM api_cache "
        "WHERE cache_key = ? AND expires_at > datetime('now')",
        (cache_key,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return json.loads(row["data_json"])


async def set_cached_data(
    cache_key: str,
    source: str,
    data: dict,
    ttl_seconds: int,
    db: aiosqlite.Connection,
) -> None:
    """Inserts or replaces a cache entry with an expiry computed from ttl_seconds."""
    await db.execute(
        """
        INSERT OR REPLACE INTO api_cache (cache_key, source, data_json, fetched_at, expires_at)
        VALUES (
            ?, ?, ?,
            datetime('now'),
            datetime('now', ? || ' seconds')
        )
        """,
        (cache_key, source, json.dumps(data), str(ttl_seconds)),
    )
    await db.commit()


async def get_ballot_items_for_election(
    election_id: str,
    db: aiosqlite.Connection,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (measures, candidates) for an election, each as a list of dicts.
    Both lists are ordered by race_type then title/name.
    """
    cursor = await db.execute(
        "SELECT m.*, r.race_type, r.title as race_title "
        "FROM measures m JOIN races r ON m.race_id = r.id "
        "WHERE r.election_id = ? ORDER BY r.race_type, m.short_title",
        (election_id,),
    )
    measures = [dict(row) for row in await cursor.fetchall()]

    cursor = await db.execute(
        "SELECT c.*, r.race_type, r.title as race_title "
        "FROM candidates c JOIN races r ON c.race_id = r.id "
        "WHERE r.election_id = ? ORDER BY r.race_type, c.name",
        (election_id,),
    )
    candidates = [dict(row) for row in await cursor.fetchall()]

    return measures, candidates


async def find_upcoming_fl_election(
    db: aiosqlite.Connection,
) -> dict | None:
    """
    Returns the nearest future Florida election, or None if none scheduled.
    """
    cursor = await db.execute(
        "SELECT id, name, election_date FROM elections "
        "WHERE state = 'FL' AND is_historical = 0 AND election_date >= date('now') "
        "ORDER BY election_date ASC LIMIT 1",
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def expire_stale_cache(db: aiosqlite.Connection) -> int:
    """
    Deletes cache entries that expired more than 1 day ago.
    Returns the count of deleted rows.
    Called on startup to prevent unbounded cache table growth.
    """
    cursor = await db.execute(
        "DELETE FROM api_cache WHERE expires_at < datetime('now', '-1 day')"
    )
    await db.commit()
    return cursor.rowcount
