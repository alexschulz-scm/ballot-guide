"""
Tests for apps/api/orchestrator/runner.py — stage sequencing.

All stage functions are monkeypatched to return canned results.
No real Claude calls or MCP calls in these tests.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from apps.api.orchestrator.events import (
    BallotFoundEvent,
    ClarificationNeededEvent,
    ErrorEvent,
    IntakeCompleteEvent,
    ItemAnalyzedEvent,
    RankingCompleteEvent,
    ReportCompleteEvent,
)
from apps.api.orchestrator.runner import run_orchestrator
from apps.api.orchestrator.schemas import (
    BallotReport,
    ElectionSummary,
    IntakeResult,
    MeasureAnalysis,
    PrecinctInfo,
    RaceAnalysis,
    RelevanceScore,
    SourceCitation,
)
from apps.api.orchestrator.stages.ballot_resolver import BallotResolverResult
from mcp_servers.shared.models import (
    BallotResponse,
    MeasureSummary,
    RaceSummary,
)
from mcp_servers.shared.models import (
    ElectionSummary as MCPElectionSummary,
    PrecinctInfo as MCPPrecinctInfo,
)


# ─────────────────────────────────────────────
# Canned stage results
# ─────────────────────────────────────────────

_FAKE_SOURCE = SourceCitation(
    name="Test", url="https://example.com", bias_rating=None, fetched_at="2026-03-01T00:00:00Z"
)

_FAKE_INTAKE = IntakeResult(
    zip_code="33101",
    address_full=None,
    priorities=["housing"],
    priorities_raw="housing",
    display_name="Maria",
    needs_clarification=False,
    clarification_question=None,
)

_FAKE_INTAKE_CLARIFICATION = IntakeResult(
    zip_code="",
    address_full=None,
    priorities=[],
    priorities_raw="",
    display_name=None,
    needs_clarification=True,
    clarification_question="What is your zip code?",
)

_FAKE_MCP_ELECTION = MCPElectionSummary(
    id="FL-2026-GEN", name="2026 FL General", date="2026-11-03", state="FL"
)
_FAKE_MCP_PRECINCT = MCPPrecinctInfo(county="Miami-Dade", district=None, precinct_id=None)

_FAKE_BALLOT = BallotResponse(
    election=_FAKE_MCP_ELECTION,
    precinct=_FAKE_MCP_PRECINCT,
    races=[RaceSummary(id="R1", title="Governor", type="state", candidate_ids=["C1"])],
    measures=[MeasureSummary(id="M1", type="constitutional_amendment", short_title="Amendment 1", full_title="Amendment 1 - Housing", topic_tags=["housing"])],
    sources=[],
    cache_hit=False,
    data_completeness="full",
)

_FAKE_MEASURE_ANALYSIS = MeasureAnalysis(
    measure_id="M1",
    short_title="Amendment 1",
    plain_english_summary="Test.",
    what_yes_means="Yes.",
    what_no_means="No.",
    fiscal_impact=None,
    fiscal_impact_source=None,
    proponent_argument="Pro.",
    opponent_argument="Con.",
    proponent_source="https://example.com/pro",
    opponent_source="https://example.com/con",
    topic_tags=["housing"],
    data_completeness="full",
    sources=[_FAKE_SOURCE],
)

_FAKE_RACE_ANALYSIS = RaceAnalysis(
    race_id="R1",
    race_title="Governor",
    race_type="state",
    candidates=[],
    data_completeness="partial",
    sources=[_FAKE_SOURCE],
)

_FAKE_SCORES = [
    RelevanceScore(
        item_id="M1", item_type="measure",
        relevance_score=8, relevance_reason="Affects housing.",
        matched_priorities=["housing"],
    ),
    RelevanceScore(
        item_id="R1", item_type="race",
        relevance_score=5, relevance_reason="State race.",
        matched_priorities=[],
    ),
]


# ─────────────────────────────────────────────
# Monkeypatch helpers
# ─────────────────────────────────────────────


def _patch_stages(monkeypatch, intake=None, ballot=None, measure=None, race=None, ranking=None):
    """Patch all stage functions with canned results."""
    intake = intake or _FAKE_INTAKE

    async def mock_load_messages(sid, db_path, max_tokens=20_000):
        return []

    async def mock_intake(msg, history, db_path):
        return intake

    async def mock_ballot(sid, zc, eid, db_path):
        if ballot is not None:
            return ballot
        return BallotResolverResult(
            event=BallotFoundEvent(
                event_type="ballot_found", session_id=sid,
                timestamp=datetime.now(timezone.utc).isoformat(),
                election_name="2026 FL General", item_count=2,
                message="Found — 2 items.",
            ),
            ballot=_FAKE_BALLOT,
        )

    async def mock_measure(ms, priorities, db_path):
        return measure if measure is not None else _FAKE_MEASURE_ANALYSIS

    async def mock_race(r, priorities, db_path):
        return race if race is not None else _FAKE_RACE_ANALYSIS

    async def mock_ranking(measures, races, priorities):
        return ranking if ranking is not None else _FAKE_SCORES

    async def mock_update_intake(*a, **kw):
        pass

    async def mock_update_ballot(*a, **kw):
        pass

    async def mock_save_report(*a, **kw):
        pass

    async def mock_compute_version(eid, db_path):
        return "abcdef1234567890"

    async def mock_get_session(sid, db_path):
        return {"report_json": None, "ballot_id": None}

    monkeypatch.setattr("apps.api.orchestrator.runner.load_messages", mock_load_messages)
    monkeypatch.setattr("apps.api.orchestrator.runner.get_session", mock_get_session)
    monkeypatch.setattr("apps.api.orchestrator.runner.run_intake", mock_intake)
    monkeypatch.setattr("apps.api.orchestrator.runner.run_ballot_resolver", mock_ballot)
    monkeypatch.setattr("apps.api.orchestrator.runner.run_measure_analysis", mock_measure)
    monkeypatch.setattr("apps.api.orchestrator.runner.run_candidate_analysis", mock_race)
    monkeypatch.setattr("apps.api.orchestrator.runner.run_relevance_ranking", mock_ranking)
    monkeypatch.setattr("apps.api.orchestrator.runner.update_session_after_intake", mock_update_intake)
    monkeypatch.setattr("apps.api.orchestrator.runner.update_session_after_ballot", mock_update_ballot)
    monkeypatch.setattr("apps.api.orchestrator.runner.save_report", mock_save_report)
    monkeypatch.setattr("apps.api.orchestrator.runner._compute_current_data_version", mock_compute_version)


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_yields_intake_complete_then_ballot_found(monkeypatch):
    _patch_stages(monkeypatch)
    events = [e async for e in run_orchestrator("sess-1", "33101 housing", "/tmp/test.db")]
    types = [e.event_type for e in events]
    assert types[0] == "intake_complete"
    assert "ballot_found" in types


@pytest.mark.asyncio
async def test_runner_yields_clarification_when_needed(monkeypatch):
    _patch_stages(monkeypatch, intake=_FAKE_INTAKE_CLARIFICATION)
    events = [e async for e in run_orchestrator("sess-2", "hello", "/tmp/test.db")]
    assert len(events) == 1
    assert events[0].event_type == "clarification_needed"
    assert events[0].question == "What is your zip code?"


@pytest.mark.asyncio
async def test_runner_stops_on_ballot_error(monkeypatch):
    error_event = ErrorEvent(
        event_type="error", session_id="sess-3",
        timestamp=datetime.now(timezone.utc).isoformat(),
        error_code="BALLOT_NOT_FOUND",
        message="No ballot found.", recoverable=False,
    )
    _patch_stages(monkeypatch, ballot=error_event)
    events = [e async for e in run_orchestrator("sess-3", "33101 housing", "/tmp/test.db")]
    types = [e.event_type for e in events]
    assert "intake_complete" in types
    assert "error" in types
    # No further events after error
    assert "item_analyzed" not in types
    assert "report_complete" not in types


@pytest.mark.asyncio
async def test_runner_yields_item_analyzed_for_each_item(monkeypatch):
    _patch_stages(monkeypatch)
    events = [e async for e in run_orchestrator("sess-4", "33101 housing", "/tmp/test.db")]
    analyzed = [e for e in events if e.event_type == "item_analyzed"]
    # _FAKE_BALLOT has 1 measure + 1 race = 2 items
    assert len(analyzed) == 2
    assert analyzed[0].items_complete == 1
    assert analyzed[1].items_complete == 2
    assert analyzed[1].items_total == 2


@pytest.mark.asyncio
async def test_runner_yields_ranking_and_report_complete(monkeypatch):
    _patch_stages(monkeypatch)
    events = [e async for e in run_orchestrator("sess-5", "33101 housing", "/tmp/test.db")]
    types = [e.event_type for e in events]
    assert "ranking_complete" in types
    assert "report_complete" in types
    report_event = [e for e in events if e.event_type == "report_complete"][0]
    assert report_event.report.session_id == "sess-5"


@pytest.mark.asyncio
async def test_runner_saves_report_to_store(monkeypatch):
    saved = []

    async def capture_save(sid, rj, dv, db_path):
        saved.append((sid, dv))

    _patch_stages(monkeypatch)
    monkeypatch.setattr("apps.api.orchestrator.runner.save_report", capture_save)
    events = [e async for e in run_orchestrator("sess-6", "33101 housing", "/tmp/test.db")]
    assert len(saved) == 1
    assert saved[0][0] == "sess-6"
    assert saved[0][1] == "abcdef1234567890"


@pytest.mark.asyncio
async def test_runner_does_not_yield_done_event(monkeypatch):
    """DoneEvent is the router's responsibility, not the runner's."""
    _patch_stages(monkeypatch)
    events = [e async for e in run_orchestrator("sess-7", "33101 housing", "/tmp/test.db")]
    types = [e.event_type for e in events]
    assert "done" not in types
