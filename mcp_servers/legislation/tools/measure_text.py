"""
Tool handler: get_measure_text

Fetches the raw legal text of a ballot measure. Reads from SQLite first
(using the measure_text column from seed/fetched data), then falls back
to mock or HTML fetch from the FL Legislature website.
"""

import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone

from mcp_servers.shared.mock_config import is_mock_mode

from mcp_servers.legislation.constants import (
    FL_ELECTIONS_BASE_URL,
    FL_LEGISLATURE_BASE_URL,
    MEASURE_TEXT_CACHE_TTL_SECONDS,
)
from mcp_servers.legislation.parsers.html_parser import extract_text_from_html
from mcp_servers.shared.cache import get_cached, make_cache_key, set_cached
from mcp_servers.shared.models import GetMeasureTextInput, MeasureText, ToolError

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_MEASURE_TEXT_RESPONSE: dict = {
    "raw_text": (
        "Mock legal text for testing. "
        "BE IT ENACTED by the Legislature of the State of Florida: "
        "Section 1. The following provisions shall apply. "
        "FISCAL IMPACT: Indeterminate positive fiscal impact. "
        "EFFECTIVE DATE: This act shall take effect upon becoming law."
    ),
    "source_url": FL_ELECTIONS_BASE_URL,
    "source_type": "html",
}


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------


def handle_get_measure_text(
    inp: GetMeasureTextInput, db_path: str
) -> MeasureText | ToolError:
    """Return raw legal text for a measure, cache-first, SQLite-primary."""
    cache_key = make_cache_key("measure_text", inp.measure_id)

    cached = get_cached(cache_key, db_path)
    if cached is not None:
        return MeasureText.model_validate({**cached, "cache_hit": True})

    row = _fetch_measure_row_from_sqlite(inp.measure_id, db_path)
    if row and row.get("measure_text"):
        result = _build_measure_text(
            inp.measure_id,
            row["measure_text"],
            row.get("fl_elections_url") or FL_ELECTIONS_BASE_URL,
            "html",
        )
        set_cached(cache_key, result.model_dump(), MEASURE_TEXT_CACHE_TTL_SECONDS, "sqlite", db_path)
        return result

    if is_mock_mode("MOCK_LEGISLATION_API"):
        result = _build_measure_text(
            inp.measure_id,
            MOCK_MEASURE_TEXT_RESPONSE["raw_text"],
            MOCK_MEASURE_TEXT_RESPONSE["source_url"],
            MOCK_MEASURE_TEXT_RESPONSE["source_type"],
        )
        set_cached(cache_key, result.model_dump(), MEASURE_TEXT_CACHE_TTL_SECONDS, "mock", db_path)
        return result

    try:
        raw_text = _fetch_html_text(inp.measure_id)
    except ValueError:
        return ToolError(
            error_code="MEASURE_TEXT_UNAVAILABLE",
            message=f"Could not fetch legal text for measure '{inp.measure_id}'",
            recoverable=True,
            fallback_source="fl_elections",
        )

    source_url = f"{FL_LEGISLATURE_BASE_URL}/{inp.measure_id}"
    result = _build_measure_text(inp.measure_id, raw_text, source_url, "html")
    set_cached(cache_key, result.model_dump(), MEASURE_TEXT_CACHE_TTL_SECONDS, "fl_legislature", db_path)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_measure_row_from_sqlite(measure_id: str, db_path: str) -> dict | None:
    """Return the measure_text and fl_elections_url columns, or None if not found."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT measure_text, fl_elections_url FROM measures WHERE id = ?",
            (measure_id,),
        ).fetchone()
    return dict(row) if row else None


def _fetch_html_text(measure_id: str) -> str:
    """Fetch legal text from FL Legislature website. Raises ValueError on failure."""
    url = f"{FL_LEGISLATURE_BASE_URL}/{measure_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ballot-guide/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
        return extract_text_from_html(html)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"MEASURE_TEXT_UNAVAILABLE: HTTP {exc.code}") from exc
    except Exception as exc:
        raise ValueError(f"MEASURE_TEXT_UNAVAILABLE: {exc}") from exc


def _build_measure_text(
    measure_id: str, raw_text: str, source_url: str, source_type: str
) -> MeasureText:
    """Construct a MeasureText model from fetched data."""
    return MeasureText(
        measure_id=measure_id,
        raw_text=raw_text,
        source_url=source_url,
        source_type=source_type,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        cache_hit=False,
    )
