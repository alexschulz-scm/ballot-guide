"""
Tool handler: get_candidate_detail

Returns the full structured profile of a candidate, including positions
mapped to the topic taxonomy. Reads from SQLite first, falls back to Ballotpedia.
"""

import json
import sqlite3
from datetime import datetime, timezone

from mcp_servers.ballot_data.constants import (
    CANDIDATE_CACHE_TTL_SECONDS,
    TOPIC_TAXONOMY,
)
from mcp_servers.ballot_data.sources.ballotpedia import fetch_candidate_from_ballotpedia
from mcp_servers.shared.cache import get_cached, make_cache_key, set_cached
from mcp_servers.shared.models import (
    CandidateDetail,
    CandidatePosition,
    DataCompleteness,
    DonorSummary,
    GetCandidateDetailInput,
    SourceCitation,
    ToolError,
)



def handle_get_candidate_detail(
    inp: GetCandidateDetailInput, db_path: str
) -> CandidateDetail | ToolError:
    """Return full candidate detail, cache-first, SQLite-primary."""
    cache_key = make_cache_key("candidate", inp.candidate_id)

    cached = get_cached(cache_key, db_path)
    if cached is not None:
        return CandidateDetail.model_validate({**cached, "data_completeness": cached.get("data_completeness", "full")})

    row = _fetch_candidate_from_sqlite(inp.candidate_id, db_path)

    if row is None:
        return ToolError(
            error_code="CANDIDATE_NOT_FOUND",
            message=f"Candidate '{inp.candidate_id}' not found",
            recoverable=False,
            fallback_source=None,
        )

    result = _build_candidate_detail(row, inp.topics)
    set_cached(cache_key, result.model_dump(), CANDIDATE_CACHE_TTL_SECONDS, "sqlite", db_path)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_candidate_from_sqlite(candidate_id: str, db_path: str) -> dict | None:
    """Return a candidate row joined with its race, or None if not found."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT c.*, r.election_id
            FROM candidates c
            JOIN races r ON c.race_id = r.id
            WHERE c.id = ?
            """,
            (candidate_id,),
        ).fetchone()
    return dict(row) if row else None


def _build_candidate_detail(
    row: dict, topics: list[str] | None
) -> CandidateDetail:
    """Construct a CandidateDetail model from a SQLite row dict."""
    positions = _build_positions(row.get("positions_json"), topics, row.get("ballotpedia_url"))
    sources = _build_sources_for_candidate(row)

    return CandidateDetail(
        id=row["id"],
        name=row["name"],
        party=row.get("party"),
        race_id=row["race_id"],
        bio=row.get("bio"),
        photo_url=None,
        website_url=row.get("fl_elections_url"),
        positions=positions,
        ballotpedia_url=row.get("ballotpedia_url"),
        sources=sources,
        data_completeness=_compute_candidate_completeness(row, positions),
    )


def _build_positions(
    raw_json: str | None,
    topics_filter: list[str] | None,
    source_url: str | None,
) -> dict[str, CandidatePosition]:
    """
    Parse flat {"topic": "text"} positions_json into typed CandidatePosition objects.

    Filters to TOPIC_TAXONOMY keys only, then applies the optional topics_filter.
    """
    if not raw_json:
        return {}

    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, CandidatePosition] = {}
    for topic, summary in raw.items():
        if topic not in TOPIC_TAXONOMY:
            continue
        if topics_filter is not None and topic not in topics_filter:
            continue
        result[topic] = CandidatePosition(
            topic=topic,
            summary=str(summary),
            quote=None,
            quote_source=None,
            source_url=source_url or "",
        )
    return result


def _parse_funding_summary(json_str: str | None) -> tuple[float | None, list[DonorSummary]]:
    """Parse funding_summary_json into (total_raised, top_donors)."""
    if not json_str:
        return None, []
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError:
        return None, []

    total = raw.get("total_raised")
    total_raised = float(total) if total is not None else None

    donors_raw = raw.get("top_donors", [])
    donors = []
    for d in donors_raw:
        try:
            donors.append(DonorSummary(
                name=d["name"],
                amount=float(d["amount"]),
                category=d.get("category"),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return total_raised, donors


def _compute_candidate_completeness(
    row: dict, positions: dict
) -> DataCompleteness:
    """Signal completeness based on bio, positions, and ballotpedia_url."""
    has_bio = bool(row.get("bio"))
    has_positions = bool(positions)
    has_url = bool(row.get("ballotpedia_url"))
    if has_bio and has_positions and has_url:
        return DataCompleteness.FULL
    if has_positions:
        return DataCompleteness.PARTIAL
    return DataCompleteness.LIMITED


def _build_sources_for_candidate(row: dict) -> list[SourceCitation]:
    """Build a SourceCitation list from the candidate's known URLs."""
    fetched_at = row.get("fetched_at") or datetime.now(timezone.utc).isoformat()
    sources = []
    if row.get("ballotpedia_url"):
        sources.append(SourceCitation(
            name="Ballotpedia",
            url=row["ballotpedia_url"],
            fetched_at=fetched_at,
            bias_rating=None,
        ))
    if row.get("fl_elections_url"):
        sources.append(SourceCitation(
            name="Florida Division of Elections",
            url=row["fl_elections_url"],
            fetched_at=fetched_at,
            bias_rating=None,
        ))
    if not sources:
        sources.append(SourceCitation(
            name="Florida Division of Elections",
            url="https://dos.myflorida.com/elections/",
            fetched_at=fetched_at,
            bias_rating=None,
        ))
    return sources
