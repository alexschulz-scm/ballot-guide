"""
Tests for apps/api/db/versioning.py — data_version hash and freshness check.
"""
from datetime import datetime, timedelta, timezone

import pytest

from apps.api.db.versioning import compute_data_version, check_data_freshness
from apps.api.db.connection import get_db
from scripts.seed_historical import seed_database


# ─────────────────────────────────────────────
# compute_data_version — pure function tests
# ─────────────────────────────────────────────

def test_compute_data_version_deterministic():
    v1 = compute_data_version("FL-2026-GEN", ["R1", "R2"], ["M1"], {"M1": "2026-01-01"})
    v2 = compute_data_version("FL-2026-GEN", ["R1", "R2"], ["M1"], {"M1": "2026-01-01"})
    assert v1 == v2


def test_compute_data_version_changes_on_different_fetched_at():
    v1 = compute_data_version("FL-2026-GEN", ["R1"], ["M1"], {"M1": "2026-01-01"})
    v2 = compute_data_version("FL-2026-GEN", ["R1"], ["M1"], {"M1": "2026-06-15"})
    assert v1 != v2


def test_compute_data_version_insensitive_to_input_order():
    """Sorted race_ids and measure_ids mean order of inputs doesn't matter."""
    v1 = compute_data_version("FL-2026-GEN", ["R2", "R1"], ["M2", "M1"], {"M1": "a", "M2": "b"})
    v2 = compute_data_version("FL-2026-GEN", ["R1", "R2"], ["M1", "M2"], {"M2": "b", "M1": "a"})
    assert v1 == v2


def test_compute_data_version_returns_16_chars():
    v = compute_data_version("FL-2026-GEN", [], [], {})
    assert len(v) == 16
    assert all(c in "0123456789abcdef" for c in v)


def test_compute_data_version_changes_on_election_id_change():
    v1 = compute_data_version("FL-2026-GEN", ["R1"], ["M1"], {"M1": "2026-01-01"})
    v2 = compute_data_version("FL-2026-PRI", ["R1"], ["M1"], {"M1": "2026-01-01"})
    assert v1 != v2


# ─────────────────────────────────────────────
# check_data_freshness — async DB tests
# ─────────────────────────────────────────────

async def _insert_session(
    db_path: str,
    session_id: str,
    report_json: str | None,
    report_generated_at: str | None,
    data_version: str | None,
    ballot_id: str | None,
) -> None:
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO sessions "
            "(id, report_json, report_generated_at, data_version, ballot_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, report_json, report_generated_at, data_version, ballot_id),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_check_freshness_returns_no_report_when_no_report(db_path):
    await _insert_session(db_path, "sess-noReport", None, None, None, None)
    result = await check_data_freshness("sess-noReport", db_path)
    assert result == "no_report"


@pytest.mark.asyncio
async def test_check_freshness_returns_very_stale_after_7_days(db_path):
    old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=8)).isoformat()
    await _insert_session(db_path, "sess-veryStale", '{"ok":1}', old_ts, "abc123", "FL-2022-GEN")
    result = await check_data_freshness("sess-veryStale", db_path)
    assert result == "very_stale"


@pytest.mark.asyncio
async def test_check_freshness_returns_stale_on_version_mismatch(db_path):
    await seed_database(db_path)

    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
    await _insert_session(
        db_path, "sess-stale", '{"ok":1}', recent_ts, "wrong_version_hash", "FL-2022-GEN"
    )
    result = await check_data_freshness("sess-stale", db_path)
    assert result == "stale"


@pytest.mark.asyncio
async def test_check_freshness_returns_fresh_for_recent_unchanged(db_path):
    await seed_database(db_path)

    # Compute the version that matches the seeded data.
    from apps.api.db.versioning import _compute_current_data_version
    current_version = await _compute_current_data_version("FL-2022-GEN", db_path)

    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
    await _insert_session(
        db_path, "sess-fresh", '{"ok":1}', recent_ts, current_version, "FL-2022-GEN"
    )
    result = await check_data_freshness("sess-fresh", db_path)
    assert result == "fresh"
