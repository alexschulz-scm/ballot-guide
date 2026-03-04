"""
Tests for mcp-servers/shared/models.py and mcp-servers/shared/cache.py.

All tests run offline — no external APIs, no network calls.
"""

import pytest
from pydantic import ValidationError

from mcp_servers.shared.cache import get_cached, is_expired, make_cache_key, set_cached
from mcp_servers.shared.models import (
    BallotResponse,
    DataCompleteness,
    ElectionSummary,
    MeasureSummary,
    PrecinctInfo,
    RaceSummary,
    SourceCitation,
    ToolError,
)


# ---------------------------------------------------------------------------
# Test 1: DataCompleteness enum — all three values
# ---------------------------------------------------------------------------


def test_data_completeness_all_values():
    assert DataCompleteness.FULL == "full"
    assert DataCompleteness.PARTIAL == "partial"
    assert DataCompleteness.LIMITED == "limited"

    # Enum members instantiate correctly
    assert DataCompleteness("full") is DataCompleteness.FULL
    assert DataCompleteness("partial") is DataCompleteness.PARTIAL
    assert DataCompleteness("limited") is DataCompleteness.LIMITED


# ---------------------------------------------------------------------------
# Test 2: ToolError — SCREAMING_SNAKE_CASE error_code field is present
# ---------------------------------------------------------------------------


def test_tool_error_screaming_snake_case():
    err = ToolError(
        error_code="ADDRESS_NOT_FOUND",
        message="Could not geocode the provided address.",
        recoverable=True,
        fallback_source="fl_elections",
    )
    assert err.error_code == "ADDRESS_NOT_FOUND"
    assert err.recoverable is True
    assert err.fallback_source == "fl_elections"

    # Non-recoverable error with no fallback
    err2 = ToolError(
        error_code="OUT_OF_STATE",
        message="Address is not in Florida.",
        recoverable=False,
        fallback_source=None,
    )
    assert err2.recoverable is False
    assert err2.fallback_source is None


# ---------------------------------------------------------------------------
# Test 3: BallotResponse — missing sources raises ValidationError
# ---------------------------------------------------------------------------


def test_ballot_response_requires_sources():
    election = ElectionSummary(
        id="FL-2026-GEN",
        name="2026 Florida General Election",
        date="2026-11-03",
        state="FL",
    )
    precinct = PrecinctInfo(county="Miami-Dade", district=None, precinct_id=None)

    with pytest.raises(ValidationError):
        BallotResponse(
            election=election,
            precinct=precinct,
            races=[],
            measures=[],
            # sources intentionally omitted
            cache_hit=False,
            data_completeness=DataCompleteness.LIMITED,
        )


# ---------------------------------------------------------------------------
# Test 4: make_cache_key — normalises whitespace and case
# ---------------------------------------------------------------------------


def test_make_cache_key_normalizes():
    key = make_cache_key("ballot", "  33101  ", "FL-2026-GEN")
    assert key == "ballot:33101:fl-2026-gen"

    # Multiple parts, mixed case
    key2 = make_cache_key("measure", "FL-2022-A2")
    assert key2 == "measure:fl-2022-a2"

    # Single part
    key3 = make_cache_key("finance", "  CAND_123  ")
    assert key3 == "finance:cand_123"


# ---------------------------------------------------------------------------
# Test 5: is_expired — past returns True, future returns False
# ---------------------------------------------------------------------------


def test_is_expired():
    assert is_expired("2020-01-01T00:00:00Z") is True
    assert is_expired("2020-01-01T00:00:00+00:00") is True

    assert is_expired("2099-01-01T00:00:00Z") is False
    assert is_expired("2099-01-01T00:00:00+00:00") is False


# ---------------------------------------------------------------------------
# Test 6: get_cached / set_cached — round-trip with real SQLite DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_set_cached_roundtrip(tmp_path):
    """Cache set then get returns the same data without expiry."""
    from apps.api.db.connection import run_migrations

    db_path = str(tmp_path / "test_cache.db")
    await run_migrations(db_path)

    cache_key = make_cache_key("ballot", "33101", "FL-2026-GEN")
    payload = {"election_id": "FL-2026-GEN", "races": ["governor"]}

    # Nothing cached yet
    assert get_cached(cache_key, db_path) is None

    # Store with a 60-second TTL
    set_cached(cache_key, payload, ttl_seconds=60, source="test", db_path=db_path)

    # Should retrieve the same payload
    result = get_cached(cache_key, db_path)
    assert result == payload
