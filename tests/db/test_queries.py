"""
Tests for apps/api/db/queries.py — canonical query functions.
"""
import json
import pytest

from apps.api.db.connection import run_migrations, get_db
from apps.api.db.queries import (
    load_messages_for_session,
    get_cached_data,
    set_cached_data,
    get_ballot_items_for_election,
    find_upcoming_fl_election,
    expire_stale_cache,
)


# ─────────────────────────────────────────────
# Cache queries
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_cached_data_returns_none_on_miss(db):
    result = await get_cached_data("nonexistent:key", db)
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_data_returns_data_on_valid_hit(db):
    payload = {"answer": 42}
    await set_cached_data("test:hit", "testapi", payload, ttl_seconds=3600, db=db)
    result = await get_cached_data("test:hit", db)
    assert result == payload


@pytest.mark.asyncio
async def test_get_cached_data_returns_none_on_expired_entry(db):
    # Insert an entry that expired in the past.
    await db.execute(
        "INSERT OR REPLACE INTO api_cache (cache_key, source, data_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now', '-1 hour'))",
        ("test:expired", "testapi", json.dumps({"stale": True})),
    )
    await db.commit()
    result = await get_cached_data("test:expired", db)
    assert result is None


@pytest.mark.asyncio
async def test_set_cached_data_overwrites_existing_key(db):
    await set_cached_data("test:overwrite", "api", {"v": 1}, ttl_seconds=3600, db=db)
    await set_cached_data("test:overwrite", "api", {"v": 2}, ttl_seconds=3600, db=db)
    result = await get_cached_data("test:overwrite", db)
    assert result == {"v": 2}


# ─────────────────────────────────────────────
# Message loading
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_load_messages_returns_oldest_first(db):
    await db.execute(
        "INSERT INTO sessions (id) VALUES ('sess-order')"
    )
    await db.execute(
        "INSERT INTO messages (session_id, role, content, token_count) VALUES "
        "('sess-order', 'user', 'first', 10), "
        "('sess-order', 'assistant', 'second', 10), "
        "('sess-order', 'user', 'third', 10)"
    )
    await db.commit()

    messages = await load_messages_for_session("sess-order", db, max_tokens=100)
    contents = [m["content"] for m in messages]
    assert contents == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_load_messages_never_drops_first_message(db):
    await db.execute("INSERT INTO sessions (id) VALUES ('sess-trunc')")
    for i in range(5):
        await db.execute(
            "INSERT INTO messages (session_id, role, content, token_count) "
            "VALUES ('sess-trunc', 'user', ?, 100)",
            (f"msg-{i}",),
        )
    await db.commit()

    # max_tokens=150 — only fits the first message + one more
    messages = await load_messages_for_session("sess-trunc", db, max_tokens=150)
    assert messages[0]["content"] == "msg-0"
    assert len(messages) >= 1


@pytest.mark.asyncio
async def test_load_messages_truncates_to_token_budget(db):
    await db.execute("INSERT INTO sessions (id) VALUES ('sess-budget')")
    for i in range(4):
        await db.execute(
            "INSERT INTO messages (session_id, role, content, token_count) "
            "VALUES ('sess-budget', 'user', ?, 1000)",
            (f"msg-{i}",),
        )
    await db.commit()

    # 4 * 1000 = 4000 tokens; budget is 2500 → keep first + 2 more = 3 messages (3000 tokens)
    # Actually: keep first (mandatory), then fill budget with remaining.
    # After keeping msg-0 (1000): remaining budget = 1500. msg-1 (1000) fits. msg-2 (1000) doesn't.
    messages = await load_messages_for_session("sess-budget", db, max_tokens=2500)
    total_tokens = sum(m["token_count"] for m in messages)
    assert total_tokens <= 2500
    assert messages[0]["content"] == "msg-0"  # first message always kept


@pytest.mark.asyncio
async def test_load_messages_returns_empty_for_no_messages(db):
    await db.execute("INSERT INTO sessions (id) VALUES ('sess-empty')")
    await db.commit()
    messages = await load_messages_for_session("sess-empty", db)
    assert messages == []


# ─────────────────────────────────────────────
# Ballot item queries
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ballot_items_for_election_returns_seeded_data(db, db_path):
    """Uses the seeded FL-2022-GEN election inserted by migration 002."""
    from scripts.seed_historical import seed_database
    await seed_database(db_path)

    measures, candidates = await get_ballot_items_for_election("FL-2022-GEN", db)
    assert len(measures) == 4
    assert len(candidates) >= 6


@pytest.mark.asyncio
async def test_get_ballot_items_returns_empty_for_unknown_election(db):
    measures, candidates = await get_ballot_items_for_election("FL-9999-FAKE", db)
    assert measures == []
    assert candidates == []


# ─────────────────────────────────────────────
# Upcoming election
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_upcoming_election_skips_historical(db):
    """FL-2022-GEN is historical (is_historical=1) — must not be returned."""
    result = await find_upcoming_fl_election(db)
    if result is not None:
        assert result["id"] != "FL-2022-GEN"


@pytest.mark.asyncio
async def test_find_upcoming_election_returns_nearest_future(db):
    await db.execute(
        "INSERT INTO elections (id, state, election_type, election_date, name, is_historical) "
        "VALUES ('FL-2030-GEN', 'FL', 'general', '2030-11-03', '2030 FL General', 0)"
    )
    await db.execute(
        "INSERT INTO elections (id, state, election_type, election_date, name, is_historical) "
        "VALUES ('FL-2028-GEN', 'FL', 'general', '2028-11-07', '2028 FL General', 0)"
    )
    await db.commit()

    result = await find_upcoming_fl_election(db)
    assert result is not None
    assert result["id"] == "FL-2028-GEN"


# ─────────────────────────────────────────────
# Cache expiry maintenance
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expire_stale_cache_deletes_old_entries(db):
    # Insert two entries: one very old, one still valid.
    await db.execute(
        "INSERT INTO api_cache (cache_key, source, data_json, fetched_at, expires_at) "
        "VALUES ('old:entry', 'test', '{}', datetime('now', '-3 days'), datetime('now', '-2 days'))"
    )
    await db.execute(
        "INSERT INTO api_cache (cache_key, source, data_json, fetched_at, expires_at) "
        "VALUES ('valid:entry', 'test', '{}', datetime('now'), datetime('now', '+1 hour'))"
    )
    await db.commit()

    deleted = await expire_stale_cache(db)
    assert deleted == 1

    result = await get_cached_data("valid:entry", db)
    assert result == {}


@pytest.mark.asyncio
async def test_expire_stale_cache_keeps_valid_entries(db):
    await db.execute(
        "INSERT INTO api_cache (cache_key, source, data_json, fetched_at, expires_at) "
        "VALUES ('keep:me', 'test', '{\"keep\": true}', datetime('now'), datetime('now', '+1 hour'))"
    )
    await db.commit()

    await expire_stale_cache(db)
    result = await get_cached_data("keep:me", db)
    assert result == {"keep": True}
