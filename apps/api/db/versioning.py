import hashlib
import json
from datetime import datetime, timezone

from apps.api.db.connection import get_db


def compute_data_version(
    election_id: str,
    race_ids: list[str],
    measure_ids: list[str],
    measure_fetched_ats: dict[str, str],
) -> str:
    """
    Computes a deterministic 16-character SHA256 hash representing the state
    of ballot data at a point in time.

    Pure function: no I/O, no randomness, no datetime.now().
    Same inputs always produce the same output.

    Args:
        election_id: e.g. "FL-2026-GEN"
        race_ids: all race IDs on the ballot
        measure_ids: all measure IDs on the ballot
        measure_fetched_ats: {measure_id: fetched_at_iso_string}

    Returns:
        16-character hex string (first 16 chars of SHA256)
    """
    version_input = {
        "election_id": election_id,
        "race_ids": sorted(race_ids),
        "measure_ids": sorted(measure_ids),
        "measure_fetched_ats": {
            k: measure_fetched_ats.get(k, "")
            for k in sorted(measure_fetched_ats.keys())
        },
    }
    canonical = json.dumps(version_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


async def _compute_current_data_version(election_id: str, db_path: str) -> str:
    """Fetch current race/measure data from DB and compute the version hash."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT id FROM races WHERE election_id = ?", (election_id,)
        )
        race_ids = [row["id"] for row in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT m.id, m.fetched_at FROM measures m "
            "JOIN races r ON m.race_id = r.id "
            "WHERE r.election_id = ?",
            (election_id,),
        )
        rows = await cursor.fetchall()

    measure_ids = [row["id"] for row in rows]
    measure_fetched_ats = {row["id"]: row["fetched_at"] or "" for row in rows}
    return compute_data_version(election_id, race_ids, measure_ids, measure_fetched_ats)


async def check_data_freshness(session_id: str, db_path: str) -> str:
    """
    Returns one of: "fresh", "stale", "very_stale", "no_report".

    "no_report"   — session exists but has no generated report
    "very_stale"  — report older than 7 days regardless of data changes
    "stale"       — report data_version differs from current ballot data
    "fresh"       — report is recent and data has not changed
    """
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT report_json, report_generated_at, data_version, ballot_id "
            "FROM sessions WHERE id = ?",
            (session_id,),
        )
        session = await cursor.fetchone()

    if not session or not session["report_json"]:
        return "no_report"

    generated_at = datetime.fromisoformat(session["report_generated_at"])
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    age_days = (now - generated_at).days

    if age_days > 7:
        return "very_stale"

    if not session["ballot_id"]:
        return "stale"

    current_version = await _compute_current_data_version(session["ballot_id"], db_path)

    if current_version != session["data_version"]:
        return "stale"

    return "fresh"
