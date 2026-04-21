"""
Tests for the follow-up handler (apps/api/orchestrator/stages/follow_up.py).

Covers intent detection, item matching, deeper data fetching, and trim logic.
All Claude calls and MCP handler calls are monkeypatched.
"""

import json

import pytest

from apps.api.orchestrator.stages.follow_up import (
    _detect_follow_up_intent,
    _find_candidate_ids,
    _find_item_title,
    _match_item_from_report,
    _title_matches,
    _trim_report,
    run_follow_up,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REPORT = {
    "items": [
        {
            "item_type": "measure",
            "measure": {
                "measure_id": "FL-2026-A1",
                "short_title": "Amendment 1",
            },
            "race": None,
        },
        {
            "item_type": "race",
            "measure": None,
            "race": {
                "race_id": "FL-2026-GOV",
                "race_title": "Governor Race",
                "candidates": [
                    {"candidate_id": "cand-1", "name": "Jane Doe"},
                    {"candidate_id": "cand-2", "name": "John Smith"},
                ],
            },
        },
    ]
}

_REPORT_JSON = json.dumps(_REPORT)


# ---------------------------------------------------------------------------
# _title_matches
# ---------------------------------------------------------------------------


class TestTitleMatches:
    def test_exact_match(self):
        assert _title_matches("tell me about amendment 1", "Amendment 1")

    def test_amendment_number_match(self):
        assert _title_matches("what is amendment 3?", "Amendment 3 - Property Tax")

    def test_keyword_governor(self):
        assert _title_matches("who's running for governor?", "Governor Race")

    def test_keyword_senate(self):
        assert _title_matches("tell me about the senate race", "US Senate")

    def test_no_match(self):
        assert not _title_matches("tell me about housing", "Amendment 1")

    def test_empty_title(self):
        assert not _title_matches("hello", "")


# ---------------------------------------------------------------------------
# _match_item_from_report
# ---------------------------------------------------------------------------


class TestMatchItemFromReport:
    def test_matches_measure_by_title(self):
        assert _match_item_from_report("tell me about amendment 1", _REPORT_JSON) == "FL-2026-A1"

    def test_matches_race_by_keyword(self):
        assert _match_item_from_report("who's running for governor?", _REPORT_JSON) == "FL-2026-GOV"

    def test_matches_candidate_name(self):
        assert _match_item_from_report("what about jane doe?", _REPORT_JSON) == "FL-2026-GOV"

    def test_no_match(self):
        assert _match_item_from_report("hello world", _REPORT_JSON) is None

    def test_invalid_json(self):
        assert _match_item_from_report("test", "not json") is None

    def test_none_json(self):
        assert _match_item_from_report("test", None) is None


# ---------------------------------------------------------------------------
# _detect_follow_up_intent
# ---------------------------------------------------------------------------


class TestDetectFollowUpIntent:
    def test_civics_intent(self):
        _, intent = _detect_follow_up_intent("what is a constitutional amendment?", _REPORT_JSON)
        assert intent == "civics"

    def test_civics_no_item(self):
        item_id, _ = _detect_follow_up_intent("what is a ballot measure?", _REPORT_JSON)
        assert item_id is None

    def test_finance_intent(self):
        item_id, intent = _detect_follow_up_intent("who funded the governor race?", _REPORT_JSON)
        assert intent == "finance"
        assert item_id == "FL-2026-GOV"

    def test_legal_text_intent(self):
        item_id, intent = _detect_follow_up_intent("read the amendment 1 full text", _REPORT_JSON)
        assert intent == "legal_text"
        assert item_id == "FL-2026-A1"

    def test_news_intent(self):
        item_id, intent = _detect_follow_up_intent("any news about amendment 1?", _REPORT_JSON)
        assert intent == "news"
        assert item_id == "FL-2026-A1"

    def test_detail_intent(self):
        item_id, intent = _detect_follow_up_intent("tell me more about amendment 1", _REPORT_JSON)
        assert intent == "detail"
        assert item_id == "FL-2026-A1"

    def test_general_intent_with_item(self):
        item_id, intent = _detect_follow_up_intent("amendment 1 is interesting", _REPORT_JSON)
        assert intent == "general"
        assert item_id == "FL-2026-A1"

    def test_general_intent_no_item(self):
        item_id, intent = _detect_follow_up_intent("hello", _REPORT_JSON)
        assert intent == "general"
        assert item_id is None


# ---------------------------------------------------------------------------
# _find_candidate_ids / _find_item_title
# ---------------------------------------------------------------------------


class TestReportHelpers:
    def test_find_candidate_ids(self):
        ids = _find_candidate_ids("FL-2026-GOV", _REPORT)
        assert ids == ["cand-1", "cand-2"]

    def test_find_candidate_ids_not_found(self):
        assert _find_candidate_ids("nonexistent", _REPORT) == []

    def test_find_item_title_measure(self):
        assert _find_item_title("FL-2026-A1", _REPORT) == "Amendment 1"

    def test_find_item_title_race(self):
        assert _find_item_title("FL-2026-GOV", _REPORT) == "Governor Race"

    def test_find_item_title_not_found(self):
        assert _find_item_title("nonexistent", _REPORT) is None


# ---------------------------------------------------------------------------
# _trim_report
# ---------------------------------------------------------------------------


class TestTrimReport:
    def test_short_report_unchanged(self):
        assert _trim_report("short") == "short"

    def test_long_report_truncated(self):
        long_json = "x" * 15_000
        result = _trim_report(long_json, max_chars=100)
        assert len(result) < 200
        assert result.endswith("... (truncated)")


# ---------------------------------------------------------------------------
# run_follow_up (integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_follow_up_civics(monkeypatch):
    """Civics intent skips deeper data, calls Claude, returns answer."""
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up.call_llm",
        lambda *a, **kw: _async_return("A constitutional amendment changes the state constitution."),
    )
    answer, sources = await run_follow_up(
        "what is a constitutional amendment?", [], _REPORT_JSON, "/tmp/test.db",
    )
    assert "constitutional" in answer.lower()
    assert sources == []


@pytest.mark.asyncio
async def test_run_follow_up_finance(monkeypatch):
    """Finance intent fetches deeper data via MCP, passes to Claude."""
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up.call_llm",
        lambda *a, **kw: _async_return("Jane Doe raised $5M from PACs."),
    )
    # Mock _fetch_finance to return fake data
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up._fetch_finance",
        lambda *a, **kw: '{"total_raised": 5000000}',
    )
    answer, sources = await run_follow_up(
        "who funded the governor race?", [], _REPORT_JSON, "/tmp/test.db",
    )
    assert answer
    assert sources == ["get_campaign_finance"]


@pytest.mark.asyncio
async def test_run_follow_up_legal_text(monkeypatch):
    """Legal text intent fetches measure text via MCP."""
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up.call_llm",
        lambda *a, **kw: _async_return("The amendment text reads..."),
    )
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up._fetch_measure_text",
        lambda *a, **kw: "BE IT ENACTED...",
    )
    answer, sources = await run_follow_up(
        "read the amendment 1 full text", [], _REPORT_JSON, "/tmp/test.db",
    )
    assert answer
    assert sources == ["get_measure_text"]


@pytest.mark.asyncio
async def test_run_follow_up_news(monkeypatch):
    """News intent fetches news via MCP."""
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up.call_llm",
        lambda *a, **kw: _async_return("Recent coverage discusses..."),
    )
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up._fetch_news",
        lambda *a, **kw: '{"articles": []}',
    )
    answer, sources = await run_follow_up(
        "any news about amendment 1?", [], _REPORT_JSON, "/tmp/test.db",
    )
    assert answer
    assert sources == ["search_news"]


@pytest.mark.asyncio
async def test_run_follow_up_detail(monkeypatch):
    """Detail intent fetches detail via MCP."""
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up.call_llm",
        lambda *a, **kw: _async_return("Here are details about Amendment 1..."),
    )
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.follow_up._fetch_detail",
        lambda *a, **kw: '{"summary": "test"}',
    )
    answer, sources = await run_follow_up(
        "tell me more about amendment 1", [], _REPORT_JSON, "/tmp/test.db",
    )
    assert answer
    assert sources == ["get_detail"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_return(val):
    return val
