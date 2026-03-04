"""
Tool handler: get_ballot_by_address

Returns the full ballot for a Florida voter's address. Uses Google Civic API
as primary source for address normalization, then builds from SQLite data.
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

from mcp_servers.shared.mock_config import is_mock_mode

from mcp_servers.ballot_data.constants import BALLOT_CACHE_TTL_SECONDS, VALID_STATE_CODE
from mcp_servers.ballot_data.sources.civic import (
    extract_state_from_civic_response,
    extract_zip_from_address,
    fetch_ballot_for_address,
)
from mcp_servers.shared.cache import get_cached, make_cache_key, set_cached
from mcp_servers.shared.models import (
    BallotResponse,
    DataCompleteness,
    ElectionSummary,
    GetBallotByAddressInput,
    MeasureSummary,
    PrecinctInfo,
    RaceSummary,
    SourceCitation,
    ToolError,
)


def handle_get_ballot_by_address(
    inp: GetBallotByAddressInput, db_path: str
) -> BallotResponse | ToolError:
    """Return the ballot for a Florida address, cache-first."""
    fl_error = _validate_fl_address(inp.address)
    if fl_error is not None:
        return fl_error

    election_id_or_err = inp.election_id or _resolve_upcoming_election(db_path)
    if isinstance(election_id_or_err, ToolError):
        return election_id_or_err
    election_id: str = election_id_or_err

    zip_code = extract_zip_from_address(inp.address) or inp.address
    cache_key = make_cache_key("ballot", zip_code, election_id)

    cached = get_cached(cache_key, db_path)
    if cached is not None:
        return BallotResponse.model_validate({**cached, "cache_hit": True})

    api_key = os.environ.get("GOOGLE_CIVIC_API_KEY", "")
    if not api_key and not is_mock_mode("MOCK_CIVIC_API"):
        return ToolError(
            error_code="CONFIG_ERROR",
            message="GOOGLE_CIVIC_API_KEY is not set",
            recoverable=False,
            fallback_source=None,
        )

    try:
        civic_raw = fetch_ballot_for_address(inp.address, api_key)
    except ValueError as exc:
        return ToolError(
            error_code="CIVIC_UNAVAILABLE",
            message=str(exc),
            recoverable=True,
            fallback_source="fl_elections",
        )

    state = extract_state_from_civic_response(civic_raw)
    if state and state != VALID_STATE_CODE:
        return ToolError(
            error_code="OUT_OF_STATE",
            message=f"Address is in {state}, not FL",
            recoverable=False,
            fallback_source=None,
        )

    ballot_items = _fetch_ballot_items_from_db(election_id, db_path)
    election_row = _fetch_election_row(election_id, db_path)
    result = _build_ballot_response(civic_raw, ballot_items, election_id, election_row)
    set_cached(cache_key, result.model_dump(), BALLOT_CACHE_TTL_SECONDS, "civic", db_path)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_fl_address(address: str) -> ToolError | None:
    """Return ToolError(OUT_OF_STATE) if a non-FL state code is found."""
    digits_stripped = re.sub(r"\d", "", address.upper())
    matches = re.findall(r"(?:,\s*|\s+)([A-Z]{2})(?:\s|$)", digits_stripped)
    for code in matches:
        if code != VALID_STATE_CODE:
            return ToolError(
                error_code="OUT_OF_STATE",
                message=f"Address appears to be in {code}, not FL. MVP supports Florida only.",
                recoverable=False,
                fallback_source=None,
            )
    return None


def _resolve_upcoming_election(db_path: str) -> str | ToolError:
    """Return the nearest future FL election id, or ToolError if none exists."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id FROM elections
            WHERE state = 'FL' AND is_historical = 0
              AND election_date >= date('now')
            ORDER BY election_date ASC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return ToolError(
            error_code="NO_UPCOMING_ELECTION",
            message="No upcoming FL election found in database",
            recoverable=False,
            fallback_source=None,
        )
    return row["id"]


def _fetch_ballot_items_from_db(election_id: str, db_path: str) -> dict:
    """Return races and measures for the given election from SQLite."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        races = conn.execute(
            "SELECT * FROM races WHERE election_id = ? ORDER BY race_type, title",
            (election_id,),
        ).fetchall()
        measures = conn.execute(
            """
            SELECT m.* FROM measures m
            JOIN races r ON m.race_id = r.id
            WHERE r.election_id = ?
            ORDER BY m.short_title
            """,
            (election_id,),
        ).fetchall()
        candidate_ids = conn.execute(
            """
            SELECT c.id, c.race_id FROM candidates c
            JOIN races r ON c.race_id = r.id
            WHERE r.election_id = ?
            """,
            (election_id,),
        ).fetchall()

    cids_by_race: dict[str, list[str]] = {}
    for cid_row in candidate_ids:
        cids_by_race.setdefault(cid_row["race_id"], []).append(cid_row["id"])

    return {
        "races": [dict(r) for r in races],
        "measures": [dict(m) for m in measures],
        "cids_by_race": cids_by_race,
    }


def _fetch_election_row(election_id: str, db_path: str) -> dict | None:
    """Fetch a single election row from SQLite."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM elections WHERE id = ?", (election_id,)
        ).fetchone()
    return dict(row) if row else None


def _build_ballot_response(
    civic_raw: dict,
    ballot_items: dict,
    election_id: str,
    election_row: dict | None,
) -> BallotResponse:
    """Assemble a BallotResponse from Civic API data and SQLite ballot items."""
    norm = civic_raw.get("normalizedInput", {})
    precinct = PrecinctInfo(
        county=norm.get("city", "Unknown"),
        district=None,
        precinct_id=None,
    )

    if election_row:
        election = ElectionSummary(
            id=election_row["id"],
            name=election_row["name"],
            date=election_row["election_date"],
            state=election_row["state"],
        )
    else:
        civic_election = civic_raw.get("election", {})
        election = ElectionSummary(
            id=election_id,
            name=civic_election.get("name", election_id),
            date=civic_election.get("electionDay", ""),
            state=VALID_STATE_CODE,
        )

    cids_by_race = ballot_items.get("cids_by_race", {})
    measure_race_ids = {m["race_id"] for m in ballot_items["measures"]}
    races = [
        RaceSummary(
            id=r["id"],
            type=r["race_type"],
            title=r["title"],
            candidate_ids=cids_by_race.get(r["id"], []),
        )
        for r in ballot_items["races"]
        if r["id"] not in measure_race_ids
    ]

    measures = [
        MeasureSummary(
            id=m["id"],
            type="constitutional_amendment",
            short_title=m["short_title"],
            full_title=m.get("full_title") or m["short_title"],
        )
        for m in ballot_items["measures"]
    ]

    fetched_at = datetime.now(timezone.utc).isoformat()
    sources = [
        SourceCitation(
            name="Google Civic Information API",
            url="https://www.googleapis.com/civicinfo/v2/voterinfo",
            fetched_at=fetched_at,
            bias_rating=None,
        )
    ]

    return BallotResponse(
        election=election,
        precinct=precinct,
        races=races,
        measures=measures,
        sources=sources,
        cache_hit=False,
        data_completeness=DataCompleteness.FULL if races or measures else DataCompleteness.LIMITED,
    )
