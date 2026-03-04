"""
SQLite-backed cache helpers for MCP servers.

All external API responses are stored in the api_cache table before being
returned to the caller. These helpers provide a simple get/set interface
backed by the same SQLite database used by the API layer.

Uses the synchronous sqlite3 stdlib — not aiosqlite — because MCP tool
handlers that call these functions do so in a synchronous context within
the tool execution path.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_cached(cache_key: str, db_path: str) -> dict | None:
    """
    Return cached data as a dict if a valid (non-expired) entry exists.

    Returns None if the key is not found or the entry has expired.
    Expired entries are not deleted here — they are overwritten on the
    next set_cached call.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT data_json, expires_at FROM api_cache WHERE cache_key = ?",
            (cache_key,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    if is_expired(row["expires_at"]):
        return None

    return json.loads(row["data_json"])


def set_cached(
    cache_key: str,
    data: dict,
    ttl_seconds: int,
    source: str,
    db_path: str,
) -> None:
    """
    Store data in the api_cache table with an expiry timestamp.

    Overwrites any existing entry with the same cache_key via INSERT OR REPLACE.
    """
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    data_json = json.dumps(data)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO api_cache
                (cache_key, source, data_json, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cache_key, source, data_json, fetched_at, expires_at),
        )
        conn.commit()


def is_expired(expires_at: str) -> bool:
    """
    Return True if the expires_at ISO 8601 timestamp is in the past.

    Handles both timezone-aware strings (with Z or +00:00) and naive strings
    by normalising to UTC for comparison.
    """
    # Normalise "Z" suffix to "+00:00" for fromisoformat compatibility
    normalised = expires_at.replace("Z", "+00:00")

    try:
        expiry = datetime.fromisoformat(normalised)
    except ValueError:
        # Fallback: treat unparseable strings as already expired
        return True

    # Ensure comparison is timezone-aware on both sides
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) > expiry


def make_cache_key(prefix: str, *parts: str) -> str:
    """
    Build a namespaced, normalised cache key.

    Each part is lowercased and stripped of surrounding whitespace before
    joining with colons. The prefix is not normalised — it must be a clean
    literal (e.g. "ballot", "measure", "news").

    Example:
        make_cache_key("ballot", "  33101  ", "FL-2026-GEN")
        -> "ballot:33101:fl-2026-gen"
    """
    normalised = ":".join(p.strip().lower() for p in parts)
    return f"{prefix}:{normalised}"
