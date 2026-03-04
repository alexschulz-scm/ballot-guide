"""
Tests for the migration runner and SQLite configuration.
Uses temporary file databases — in-memory SQLite does not support WAL mode
and connections do not share state across separate aiosqlite opens.
"""
import os
import tempfile

import pytest
import aiosqlite

from apps.api.db.connection import get_db, run_migrations
from apps.api.db.exceptions import MigrationError


def _temp_db_path(name: str) -> str:
    """Return a unique temp file path for a test database. SQLite creates it on connect."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"test_{name}_")
    os.close(fd)
    os.unlink(path)  # Remove so SQLite starts with a clean slate
    return path


async def _fresh_db(name: str) -> str:
    """Apply migrations to a fresh temp file DB; return the path."""
    path = _temp_db_path(name)
    await run_migrations(path)
    return path


# ─────────────────────────────────────────────
# Schema — tables and indexes
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fresh_db_has_all_8_tables():
    path = await _fresh_db("tables")
    async with get_db(path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row["name"] for row in await cursor.fetchall()}

    expected = {
        "elections", "races", "candidates", "measures",
        "api_cache", "sessions", "messages", "_migrations",
    }
    assert tables == expected


@pytest.mark.asyncio
async def test_fresh_db_has_all_7_indexes():
    path = await _fresh_db("indexes")
    async with get_db(path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row["name"] for row in await cursor.fetchall()}

    expected = {
        "idx_sessions_status",
        "idx_sessions_updated_at",
        "idx_messages_session_id",
        "idx_api_cache_expires_at",
        "idx_races_election_id",
        "idx_candidates_race_id",
        "idx_measures_race_id",
    }
    assert indexes == expected


# ─────────────────────────────────────────────
# Migration runner behaviour
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_migrations_table_records_applied_files():
    path = await _fresh_db("records")
    async with get_db(path) as db:
        cursor = await db.execute("SELECT filename FROM _migrations ORDER BY filename")
        filenames = [row["filename"] for row in await cursor.fetchall()]

    assert "001_initial.sql" in filenames
    assert "002_seed_fl_2022.sql" in filenames


@pytest.mark.asyncio
async def test_migration_idempotent_second_run_applies_nothing():
    path = await _fresh_db("idempotent")
    # Both files already applied; a second run must apply nothing.
    applied = await run_migrations(path)
    assert applied == []


@pytest.mark.asyncio
async def test_failed_migration_raises_migration_error(tmp_path, monkeypatch):
    """A migration file with bad SQL must raise MigrationError."""
    import apps.api.db.connection as conn_module

    bad_dir = tmp_path / "migrations"
    bad_dir.mkdir()
    (bad_dir / "001_bad.sql").write_text("THIS IS NOT VALID SQL", encoding="utf-8")

    monkeypatch.setattr(conn_module, "_MIGRATIONS_DIR", str(bad_dir))

    db_path = str(tmp_path / "bad.db")
    with pytest.raises(MigrationError) as exc_info:
        await run_migrations(db_path)

    assert exc_info.value.filename == "001_bad.sql"


@pytest.mark.asyncio
async def test_failed_migration_does_not_leave_partial_state(tmp_path, monkeypatch):
    """
    A migration that fails mid-way must not leave partially-created tables.
    The canary table appears before the bad statement; after rollback it must not exist.
    """
    import apps.api.db.connection as conn_module

    partial_dir = tmp_path / "migrations"
    partial_dir.mkdir()
    # Two statements: first is valid, second is invalid.
    sql = "CREATE TABLE canary (id TEXT PRIMARY KEY);\nTHIS WILL FAIL"
    (partial_dir / "001_partial.sql").write_text(sql, encoding="utf-8")

    monkeypatch.setattr(conn_module, "_MIGRATIONS_DIR", str(partial_dir))

    db_path = str(tmp_path / "partial.db")
    with pytest.raises(MigrationError):
        await run_migrations(db_path)

    # The canary table must not exist — the transaction was rolled back.
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='canary'"
        )
        assert await cursor.fetchone() is None


# ─────────────────────────────────────────────
# SQLite configuration
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wal_mode_enabled():
    path = await _fresh_db("wal")
    async with get_db(path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
    assert row[0] in ("wal", "delete")


@pytest.mark.asyncio
async def test_foreign_keys_enabled():
    path = await _fresh_db("fk")
    async with get_db(path) as db:
        cursor = await db.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
    assert row[0] == 1


# ─────────────────────────────────────────────
# Referential integrity
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cascade_delete_measures_when_race_deleted():
    path = await _fresh_db("cascade_measures")
    async with get_db(path) as db:
        await db.execute(
            "INSERT INTO elections (id, state, election_type, election_date, name) "
            "VALUES ('FL-TEST', 'FL', 'general', '2026-11-03', 'Test Election')"
        )
        await db.execute(
            "INSERT INTO races (id, election_id, race_type, title) "
            "VALUES ('FL-TEST-R1', 'FL-TEST', 'governor', 'Governor')"
        )
        await db.execute(
            "INSERT INTO measures (id, race_id, short_title) "
            "VALUES ('FL-TEST-M1', 'FL-TEST-R1', 'Test Measure')"
        )
        await db.commit()

        await db.execute("DELETE FROM races WHERE id = 'FL-TEST-R1'")
        await db.commit()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM measures WHERE id = 'FL-TEST-M1'"
        )
        count = (await cursor.fetchone())[0]

    assert count == 0


@pytest.mark.asyncio
async def test_cascade_delete_candidates_when_race_deleted():
    path = await _fresh_db("cascade_candidates")
    async with get_db(path) as db:
        await db.execute(
            "INSERT INTO elections (id, state, election_type, election_date, name) "
            "VALUES ('FL-TESTC', 'FL', 'general', '2026-11-03', 'Test Election C')"
        )
        await db.execute(
            "INSERT INTO races (id, election_id, race_type, title) "
            "VALUES ('FL-TESTC-R1', 'FL-TESTC', 'governor', 'Governor')"
        )
        await db.execute(
            "INSERT INTO candidates (id, race_id, name) "
            "VALUES ('cand_test_001', 'FL-TESTC-R1', 'Test Candidate')"
        )
        await db.commit()

        await db.execute("DELETE FROM races WHERE id = 'FL-TESTC-R1'")
        await db.commit()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM candidates WHERE id = 'cand_test_001'"
        )
        count = (await cursor.fetchone())[0]

    assert count == 0


# ─────────────────────────────────────────────
# Seed migration content
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fl_2022_election_seeded_by_002_migration():
    path = await _fresh_db("seed_002")
    async with get_db(path) as db:
        cursor = await db.execute(
            "SELECT id, name, is_historical FROM elections WHERE id = 'FL-2022-GEN'"
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row["name"] == "2022 Florida General Election"
    assert row["is_historical"] == 1
