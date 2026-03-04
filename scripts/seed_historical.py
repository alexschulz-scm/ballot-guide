#!/usr/bin/env python3
"""
Load FL 2022 historical election seed data into SQLite.

Usage:
    python scripts/seed_historical.py --db /data/ballot-guide.db
    python scripts/seed_historical.py --db /data/ballot-guide.db --replace
    python scripts/seed_historical.py --db /data/ballot-guide.db --dry-run
"""
import argparse
import asyncio
import json
import os
import sys

# Ensure repo root is on sys.path when script is run directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiosqlite

from apps.api.db.connection import run_migrations

_SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "seed")
_ELECTION_ID = "FL-2022-GEN"

_REQUIRED_MEASURE_FIELDS = {"id", "race_id", "short_title", "passed", "yes_pct", "no_pct"}
_REQUIRED_CANDIDATE_FIELDS = {"id", "race_id", "name", "data_completeness"}


# ─────────────────────────────────────────────
# File loading and validation
# ─────────────────────────────────────────────

def load_seed_files() -> tuple[dict, list, list]:
    """
    Loads and validates the three seed JSON files.
    Returns (election_data, measures, candidates).
    Raises ValueError with clear message if any file is missing or malformed.
    """
    files = {
        "fl_2022_election.json": None,
        "fl_2022_measures.json": None,
        "fl_2022_candidates.json": None,
    }
    for filename in files:
        path = os.path.join(_SEED_DIR, filename)
        if not os.path.exists(path):
            raise ValueError(f"Seed file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            try:
                files[filename] = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {filename}: {exc}") from exc

    election_data = files["fl_2022_election.json"]
    measures = files["fl_2022_measures.json"]
    candidates = files["fl_2022_candidates.json"]

    if not isinstance(election_data, dict) or "election" not in election_data:
        raise ValueError("fl_2022_election.json must be an object with an 'election' key")
    if not isinstance(measures, list):
        raise ValueError("fl_2022_measures.json must be a JSON array")
    if not isinstance(candidates, list):
        raise ValueError("fl_2022_candidates.json must be a JSON array")

    return election_data, measures, candidates


def validate_seed_data(
    election_data: dict, measures: list, candidates: list
) -> list[str]:
    """
    Validates seed data against expected schema.
    Returns list of validation errors (empty list = valid).
    Does NOT write to DB.
    """
    errors: list[str] = []

    if "races" not in election_data or not election_data["races"]:
        errors.append("election_data must contain a non-empty 'races' list")

    for i, measure in enumerate(measures):
        missing = _REQUIRED_MEASURE_FIELDS - measure.keys()
        if missing:
            errors.append(f"Measure[{i}] missing fields: {missing}")
        if measure.get("passed") is None:
            errors.append(f"Measure[{i}] '{measure.get('id')}': passed must not be null")
        if measure.get("positions_json") is not None:
            try:
                json.loads(measure["positions_json"])
            except (json.JSONDecodeError, TypeError):
                errors.append(f"Measure[{i}] has invalid positions_json")

    for i, candidate in enumerate(candidates):
        missing = _REQUIRED_CANDIDATE_FIELDS - candidate.keys()
        if missing:
            errors.append(f"Candidate[{i}] missing fields: {missing}")
        if candidate.get("positions_json") is not None:
            try:
                json.loads(candidate["positions_json"])
            except (json.JSONDecodeError, TypeError):
                errors.append(f"Candidate[{i}] '{candidate.get('id')}' has invalid positions_json")
        if candidate.get("funding_summary_json") is not None:
            try:
                json.loads(candidate["funding_summary_json"])
            except (json.JSONDecodeError, TypeError):
                errors.append(f"Candidate[{i}] '{candidate.get('id')}' has invalid funding_summary_json")

    return errors


# ─────────────────────────────────────────────
# Database operations
# ─────────────────────────────────────────────

async def _insert_election(db: aiosqlite.Connection, election_data: dict) -> None:
    elec = election_data["election"]
    await db.execute(
        """
        INSERT OR IGNORE INTO elections
            (id, state, election_type, election_date, name, is_historical)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            elec["id"], elec["state"], elec["election_type"],
            elec["election_date"], elec["name"], elec.get("is_historical", 0),
        ),
    )
    for race in election_data["races"]:
        await db.execute(
            """
            INSERT OR IGNORE INTO races
                (id, election_id, race_type, title, district)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                race["id"], race["election_id"], race["race_type"],
                race["title"], race.get("district"),
            ),
        )


async def _insert_measures(db: aiosqlite.Connection, measures: list) -> None:
    for m in measures:
        await db.execute(
            """
            INSERT OR IGNORE INTO measures
                (id, race_id, short_title, full_title, measure_text, plain_summary,
                 fiscal_impact, fiscal_impact_source, proponent_argument,
                 opponent_argument, topic_tags_json, passed, yes_pct, no_pct,
                 sources_json, ballotpedia_url, fl_elections_url, fetched_at,
                 data_completeness)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m["id"], m["race_id"], m["short_title"],
                m.get("full_title"), m.get("measure_text"), m.get("plain_summary"),
                m.get("fiscal_impact"), m.get("fiscal_impact_source"),
                m.get("proponent_argument"), m.get("opponent_argument"),
                m.get("topic_tags_json"), m.get("passed"),
                m.get("yes_pct"), m.get("no_pct"),
                m.get("sources_json"), m.get("ballotpedia_url"),
                m.get("fl_elections_url"), m.get("fetched_at"),
                m.get("data_completeness", "limited"),
            ),
        )


async def _insert_candidates(db: aiosqlite.Connection, candidates: list) -> None:
    for c in candidates:
        await db.execute(
            """
            INSERT OR IGNORE INTO candidates
                (id, race_id, name, party, bio, positions_json,
                 funding_summary_json, ballotpedia_url, fl_elections_url,
                 fetched_at, data_completeness)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c["id"], c["race_id"], c["name"], c.get("party"),
                c.get("bio"), c.get("positions_json"), c.get("funding_summary_json"),
                c.get("ballotpedia_url"), c.get("fl_elections_url"),
                c.get("fetched_at"), c.get("data_completeness", "limited"),
            ),
        )


async def seed_database(db_path: str, replace: bool = False) -> dict:
    """
    Inserts seed data into the database.
    Returns counts: {"elections": 1, "races": N, "measures": N, "candidates": N}
    """
    election_data, measures, candidates = load_seed_files()

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")

        if replace:
            await db.execute("BEGIN")
            await db.execute(
                "DELETE FROM elections WHERE id = ?", (_ELECTION_ID,)
            )
            await _insert_election(db, election_data)
            await _insert_measures(db, measures)
            await _insert_candidates(db, candidates)
            await db.commit()
        else:
            await _insert_election(db, election_data)
            await _insert_measures(db, measures)
            await _insert_candidates(db, candidates)
            await db.commit()

    return {
        "elections": 1,
        "races": len(election_data["races"]),
        "measures": len(measures),
        "candidates": len(candidates),
    }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FL 2022 historical election data")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--replace", action="store_true", help="Delete and re-insert FL 2022 data")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no DB writes")
    args = parser.parse_args()

    try:
        election_data, measures, candidates = load_seed_files()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    errors = validate_seed_data(election_data, measures, candidates)

    if args.dry_run:
        if errors:
            print("Validation FAILED:")
            for err in errors:
                print(f"  - {err}")
            sys.exit(1)
        print("Validation passed.")
        print(
            f"Would insert: 1 election, {len(election_data['races'])} races, "
            f"{len(measures)} measures, {len(candidates)} candidates"
        )
        _print_null_warnings(measures, candidates)
        sys.exit(0)

    if errors:
        print("Validation FAILED — aborting:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    try:
        counts = asyncio.run(seed_database(args.db, replace=args.replace))
    except Exception as exc:
        print(f"ERROR: Seed failed: {exc}", file=sys.stderr)
        sys.exit(1)

    action = "Replaced" if args.replace else "Seeded"
    print(
        f"{action} {_ELECTION_ID}: "
        f"{counts['elections']} election, {counts['races']} races, "
        f"{counts['measures']} measures, {counts['candidates']} candidates"
    )


def _print_null_warnings(measures: list, candidates: list) -> None:
    for m in measures:
        for field in ("measure_text", "plain_summary", "fiscal_impact", "proponent_argument", "opponent_argument"):
            if m.get(field) is None:
                print(f"  WARNING: measure {m['id']} has null {field}")
    for c in candidates:
        for field in ("bio", "positions_json", "funding_summary_json"):
            if c.get(field) is None:
                print(f"  WARNING: candidate {c['id']} has null {field}")


if __name__ == "__main__":
    main()
