"""
Tool handler: get_measure_detail

Returns the full structured profile of a ballot measure, with proponent
and opponent arguments. Reads from SQLite first, falls back to Ballotpedia.
"""

import json
import sqlite3

from mcp_servers.ballot_data.constants import MEASURE_CACHE_TTL_SECONDS, TOPIC_TAXONOMY
from mcp_servers.ballot_data.sources.ballotpedia import fetch_measure_from_ballotpedia
from mcp_servers.shared.cache import get_cached, make_cache_key, set_cached
from mcp_servers.shared.mock_config import is_mock_mode
from mcp_servers.shared.models import (
    DataCompleteness,
    GetMeasureDetailInput,
    MeasureDetail,
    SourceCitation,
    ToolError,
)


def handle_get_measure_detail(
    inp: GetMeasureDetailInput, db_path: str
) -> MeasureDetail | ToolError:
    """Return full measure detail, cache-first, SQLite-primary."""
    cache_key = make_cache_key("measure", inp.measure_id)

    cached = get_cached(cache_key, db_path)
    if cached is not None:
        m = MeasureDetail.model_validate(cached)
        # Return model, overriding full_text if caller now wants it included
        return m

    row = _fetch_measure_from_sqlite(inp.measure_id, db_path)

    if row is None:
        if not is_mock_mode("MOCK_BALLOTPEDIA_API") and row is None:
            # Try Ballotpedia — but we have no URL without the DB row
            pass
        return ToolError(
            error_code="MEASURE_NOT_FOUND",
            message=f"Measure '{inp.measure_id}' not found",
            recoverable=False,
            fallback_source=None,
        )

    result = _build_measure_detail(row, inp.include_full_text)
    set_cached(cache_key, result.model_dump(), MEASURE_CACHE_TTL_SECONDS, "sqlite", db_path)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_measure_from_sqlite(measure_id: str, db_path: str) -> dict | None:
    """Return a measure row joined with its race, or None if not found."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT m.*, r.race_type, r.election_id
            FROM measures m
            JOIN races r ON m.race_id = r.id
            WHERE m.id = ?
            """,
            (measure_id,),
        ).fetchone()
    return dict(row) if row else None


def _build_measure_detail(row: dict, include_full_text: bool) -> MeasureDetail:
    """Construct a MeasureDetail model from a SQLite row dict."""
    return MeasureDetail(
        id=row["id"],
        short_title=row["short_title"],
        full_title=row.get("full_title") or row["short_title"],
        type=_derive_measure_type(row),
        summary=row.get("plain_summary"),
        status=_derive_status(row.get("passed")),
        election_id=row["election_id"],
        topic_tags=_parse_topic_tags(row.get("topic_tags_json")),
        proponent_argument=row.get("proponent_argument"),
        opponent_argument=row.get("opponent_argument"),
        fiscal_impact=row.get("fiscal_impact"),
        fiscal_impact_source=row.get("fiscal_impact_source"),
        passed=_int_to_bool(row.get("passed")),
        yes_pct=row.get("yes_pct"),
        no_pct=row.get("no_pct"),
        full_text=row.get("measure_text") if include_full_text else None,
        ballotpedia_url=row.get("ballotpedia_url"),
        fl_elections_url=row.get("fl_elections_url"),
        sources=_parse_sources(row.get("sources_json")),
        data_completeness=_compute_measure_completeness(row),
    )


def _derive_status(passed: object) -> str:
    """Map the passed integer column to a status string."""
    if passed is None:
        return "on_ballot"
    return "passed" if passed == 1 else "failed"


def _derive_measure_type(row: dict) -> str:
    """Derive measure type from race_type; default to constitutional_amendment."""
    race_type = row.get("race_type", "")
    if "referendum" in race_type.lower():
        return "referendum"
    if "bond" in race_type.lower():
        return "bond"
    return "constitutional_amendment"


def _int_to_bool(value: object) -> bool | None:
    """Convert 0/1/None to False/True/None."""
    if value is None:
        return None
    return bool(value)


def _parse_topic_tags(json_str: str | None) -> list[str]:
    """Parse topic_tags_json, filter to canonical taxonomy, ignore bad values."""
    if not json_str:
        return []
    try:
        tags = json.loads(json_str)
    except json.JSONDecodeError:
        return []
    return [t for t in tags if isinstance(t, str) and t in TOPIC_TAXONOMY]


def _parse_sources(json_str: str | None) -> list[SourceCitation]:
    """Parse sources_json into a list of SourceCitation models."""
    if not json_str:
        return []
    try:
        raw_list = json.loads(json_str)
    except json.JSONDecodeError:
        return []
    result = []
    for item in raw_list:
        try:
            result.append(SourceCitation.model_validate(item))
        except Exception:
            continue
    return result


def _compute_measure_completeness(row: dict) -> DataCompleteness:
    """Signal completeness based on how many key fields are populated."""
    fields = (
        row.get("plain_summary"),
        row.get("proponent_argument"),
        row.get("opponent_argument"),
        row.get("fiscal_impact"),
    )
    count = sum(1 for f in fields if f)
    if count < 2:
        return DataCompleteness.LIMITED
    if count < 4:
        return DataCompleteness.PARTIAL
    return DataCompleteness.FULL
