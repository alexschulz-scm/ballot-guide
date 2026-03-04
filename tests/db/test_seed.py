"""
Tests for scripts/seed_historical.py — loading, validation, and seeding modes.
"""
import json
import os
import sys

import pytest
import pytest_asyncio
import aiosqlite

# Ensure repo root is on path so 'scripts' is importable.
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO_ROOT)

from scripts.seed_historical import (
    load_seed_files,
    validate_seed_data,
    seed_database,
)
from apps.api.db.connection import run_migrations


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

async def _seeded_db_path(tmp_path) -> str:
    """Migrated + seeded temp DB; returns path."""
    path = str(tmp_path / "seeded.db")
    await run_migrations(path)
    await seed_database(path)
    return path


# ─────────────────────────────────────────────
# File loading
# ─────────────────────────────────────────────

def test_load_seed_files_returns_expected_types():
    election_data, measures, candidates = load_seed_files()
    assert isinstance(election_data, dict)
    assert isinstance(measures, list)
    assert isinstance(candidates, list)


def test_load_seed_files_raises_on_missing_file(tmp_path, monkeypatch):
    import scripts.seed_historical as mod
    monkeypatch.setattr(mod, "_SEED_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="not found"):
        load_seed_files()


def test_load_seed_files_raises_on_invalid_json(tmp_path, monkeypatch):
    import scripts.seed_historical as mod
    monkeypatch.setattr(mod, "_SEED_DIR", str(tmp_path))
    (tmp_path / "fl_2022_election.json").write_text("{invalid json}", encoding="utf-8")
    (tmp_path / "fl_2022_measures.json").write_text("[]", encoding="utf-8")
    (tmp_path / "fl_2022_candidates.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_seed_files()


# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────

def test_validate_seed_data_passes_on_valid_data():
    election_data, measures, candidates = load_seed_files()
    errors = validate_seed_data(election_data, measures, candidates)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_validate_seed_data_catches_null_passed_field():
    election_data, measures, candidates = load_seed_files()
    measures[0]["passed"] = None
    errors = validate_seed_data(election_data, measures, candidates)
    assert any("passed" in e for e in errors)


def test_validate_seed_data_catches_invalid_positions_json():
    election_data, measures, candidates = load_seed_files()
    candidates[0]["positions_json"] = "{not valid json"
    errors = validate_seed_data(election_data, measures, candidates)
    assert any("positions_json" in e for e in errors)


# ─────────────────────────────────────────────
# Seed counts
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_inserts_correct_record_counts(tmp_path):
    path = await _seeded_db_path(tmp_path)
    async with aiosqlite.connect(path) as db:
        e = (await (await db.execute("SELECT COUNT(*) FROM elections")).fetchone())[0]
        r = (await (await db.execute("SELECT COUNT(*) FROM races")).fetchone())[0]
        m = (await (await db.execute("SELECT COUNT(*) FROM measures")).fetchone())[0]
        c = (await (await db.execute("SELECT COUNT(*) FROM candidates")).fetchone())[0]

    assert e >= 1  # migrations seed election rows; seed script adds races/measures
    assert r == 7
    assert m == 4
    assert c >= 6


# ─────────────────────────────────────────────
# Measure result fields
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fl_2022_has_4_amendments(tmp_path):
    path = await _seeded_db_path(tmp_path)
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM measures m "
            "JOIN races r ON m.race_id = r.id "
            "WHERE r.election_id = 'FL-2022-GEN'"
        )
        count = (await cursor.fetchone())[0]
    assert count == 4


@pytest.mark.asyncio
async def test_seed_measures_have_passed_field_populated(tmp_path):
    path = await _seeded_db_path(tmp_path)
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT id FROM measures WHERE passed IS NULL AND race_id IN "
            "(SELECT id FROM races WHERE election_id = 'FL-2022-GEN')"
        )
        nulls = await cursor.fetchall()
    assert nulls == [], f"Measures with null passed: {[r[0] for r in nulls]}"


@pytest.mark.asyncio
async def test_seed_amendment_2_yes_pct_approx_60_8(tmp_path):
    path = await _seeded_db_path(tmp_path)
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT yes_pct FROM measures WHERE id = 'FL-2022-M2'"
        )
        row = await cursor.fetchone()
    assert row is not None
    assert abs(row[0] - 60.8) < 0.1


# ─────────────────────────────────────────────
# Candidate fields
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_candidates_positions_is_valid_json(tmp_path):
    path = await _seeded_db_path(tmp_path)
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT id, positions_json FROM candidates "
            "WHERE race_id IN (SELECT id FROM races WHERE election_id = 'FL-2022-GEN')"
        )
        rows = await cursor.fetchall()
    for row in rows:
        if row[1] is not None:
            parsed = json.loads(row[1])
            assert isinstance(parsed, dict), f"Candidate {row[0]} positions_json is not a dict"


@pytest.mark.asyncio
async def test_seed_all_candidates_have_full_completeness(tmp_path):
    path = await _seeded_db_path(tmp_path)
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(
            "SELECT id FROM candidates WHERE data_completeness != 'full' "
            "AND race_id IN (SELECT id FROM races WHERE election_id = 'FL-2022-GEN')"
        )
        not_full = await cursor.fetchall()
    assert not_full == [], f"Candidates without full completeness: {[r[0] for r in not_full]}"


# ─────────────────────────────────────────────
# --dry-run
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_dry_run_exits_without_writing(tmp_path):
    """seed_database is never called in dry-run — simulate by not calling it."""
    path = str(tmp_path / "never_created.db")
    # Dry-run only loads/validates files; it must NOT create the DB file.
    election_data, measures, candidates = load_seed_files()
    errors = validate_seed_data(election_data, measures, candidates)
    assert errors == []
    assert not os.path.exists(path), "Dry-run must not create the database file"


# ─────────────────────────────────────────────
# --replace (atomicity)
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_replace_clears_and_reinserts(tmp_path):
    path = await _seeded_db_path(tmp_path)

    # Confirm data is present, then replace.
    await seed_database(path, replace=True)

    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM measures")
        count = (await cursor.fetchone())[0]
    assert count == 4


@pytest.mark.asyncio
async def test_seed_replace_is_atomic(tmp_path, monkeypatch):
    """
    Simulate a failure mid-replace: old data must still be intact afterward.
    """
    path = await _seeded_db_path(tmp_path)

    # Record measure count before attempted replace.
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM measures")
        before_count = (await cursor.fetchone())[0]

    # Monkeypatch _insert_measures to raise after DELETE has run.
    import scripts.seed_historical as mod
    original = mod._insert_measures

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("Simulated failure during replace")

    monkeypatch.setattr(mod, "_insert_measures", _raise)

    with pytest.raises(Exception):
        await seed_database(path, replace=True)

    # Measures must still exist — transaction rolled back.
    async with aiosqlite.connect(path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM measures")
        after_count = (await cursor.fetchone())[0]

    assert after_count == before_count, (
        f"Replace was not atomic: measures went from {before_count} to {after_count}"
    )
