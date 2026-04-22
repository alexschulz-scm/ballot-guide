"""
Tests for all orchestrator stages (Session 3C).
All Claude calls and MCP handler calls are monkeypatched — no real API calls.
"""
import asyncio
import inspect
import json

import pytest

from apps.api.orchestrator.events import ErrorEvent
from apps.api.orchestrator.schemas import (
    BallotReport,
    BallotReportItem,
    CandidateAnalysis,
    ElectionSummary,
    IntakeResult,
    MeasureAnalysis,
    PrecinctInfo,
    RaceAnalysis,
    RelevanceRanking,
    RelevanceScore,
    SourceCitation,
)
from apps.api.orchestrator.stages.ballot_resolver import run_ballot_resolver
from apps.api.orchestrator.stages.candidate_analyst import run_candidate_analysis
from apps.api.orchestrator.stages.intake import run_intake
from apps.api.orchestrator.stages.measure_analyst import run_measure_analysis
from apps.api.orchestrator.stages.relevance_ranker import run_relevance_ranking
from apps.api.orchestrator.stages.report_assembler import assemble_report
from mcp_servers.shared.models import (
    MeasureSummary,
    RaceSummary,
    ToolError,
)

# ---------------------------------------------------------------------------
# Shared JSON fixtures
# ---------------------------------------------------------------------------

_INTAKE_VALID_JSON = json.dumps({
    "zip_code": "33101",
    "address_full": None,
    "priorities": ["housing"],
    "priorities_raw": "I care about housing",
    "display_name": None,
    "needs_clarification": False,
    "clarification_question": None,
})

_INTAKE_SEVEN_PRIORITIES_JSON = json.dumps({
    "zip_code": "33101",
    "address_full": None,
    "priorities": ["housing", "education", "taxes", "healthcare",
                   "environment", "public_safety", "economy"],
    "priorities_raw": "everything",
    "display_name": None,
    "needs_clarification": False,
    "clarification_question": None,
})

_INTAKE_BAD_ZIP_JSON = json.dumps({
    "zip_code": "ABCDE",
    "address_full": None,
    "priorities": ["housing"],
    "priorities_raw": "Miami area",
    "display_name": None,
    "needs_clarification": False,
    "clarification_question": None,
})

_SOURCE = {
    "name": "Test Source",
    "url": "https://example.com",
    "bias_rating": None,
    "fetched_at": "2026-01-01T00:00:00Z",
}

_MEASURE_VALID_JSON = json.dumps({
    "measure_id": "FL-2022-M1",
    "short_title": "Amendment 1",
    "plain_english_summary": "This measure does something important.",
    "what_yes_means": "Yes means X.",
    "what_no_means": "No means Y.",
    "fiscal_impact": None,
    "fiscal_impact_source": None,
    "proponent_argument": "Supporters argue this helps.",
    "opponent_argument": "Opponents argue this hurts.",
    "proponent_source": "https://pro.example.com",
    "opponent_source": "https://con.example.com",
    "topic_tags": ["economy"],
    "data_completeness": "full",
    "sources": [_SOURCE],
})

_CANDIDATE_VALID_JSON = json.dumps({
    "candidate_id": "C-1",
    "name": "Jane Smith",
    "party": "Democratic",
    "bio_summary": "Jane Smith is a state senator.",
    "positions": {"housing": "Smith supports affordable housing tax credits."},
    "top_donors": ["Ken Griffin ($1,000,000)"],
    "funding_total": "$2.5M raised",
    "sources": [_SOURCE],
})

_SCORES_JSON_UNSORTED = json.dumps({"scores": [
    {"item_id": "FL-2022-M2", "item_type": "measure", "relevance_score": 3,
     "relevance_reason": "Amendment 2 affects tax rates.", "matched_priorities": ["taxes"]},
    {"item_id": "FL-2022-M1", "item_type": "measure", "relevance_score": 8,
     "relevance_reason": "Amendment 1 affects housing supply rules.", "matched_priorities": ["housing"]},
    {"item_id": "R-1", "item_type": "race", "relevance_score": 5,
     "relevance_reason": "Governor race involves education funding.", "matched_priorities": ["education"]},
]})

_SCORES_WITH_FORBIDDEN = json.dumps({"scores": [
    {"item_id": "FL-2022-M1", "item_type": "measure", "relevance_score": 7,
     "relevance_reason": "This measure would help you save on housing.", "matched_priorities": ["housing"]},
]})


# ---------------------------------------------------------------------------
# Helper: async mock that returns responses in sequence
# ---------------------------------------------------------------------------

def _make_call_llm_sequence(*responses: str):
    """Return an async mock that yields each response in order (repeats last)."""
    resp_list = list(responses)
    state = {"idx": 0}

    async def _mock(*args, **kwargs):
        r = resp_list[state["idx"]]
        state["idx"] = min(state["idx"] + 1, len(resp_list) - 1)
        return r

    return _mock


def _noop_mcp(*args, **kwargs):
    """MCP handler stub that returns minimal valid data."""
    from mcp_servers.shared.models import ToolError
    return ToolError(
        error_code="NO_DATA", message="stub", recoverable=False, fallback_source=None
    )


# ---------------------------------------------------------------------------
# Intake tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intake_normalizes_free_text_priority(monkeypatch):
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.intake.call_llm",
        _make_call_llm_sequence(_INTAKE_VALID_JSON),
    )
    result = await run_intake("I care about housing in Miami 33101", [], "unused.db")
    assert result.zip_code == "33101"
    assert "housing" in result.priorities
    assert not result.needs_clarification


@pytest.mark.asyncio
async def test_intake_truncates_to_5_priorities(monkeypatch):
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.intake.call_llm",
        _make_call_llm_sequence(_INTAKE_SEVEN_PRIORITIES_JSON),
    )
    result = await run_intake("I care about everything", [], "unused.db")
    assert len(result.priorities) <= 5


@pytest.mark.asyncio
async def test_intake_invalid_zip_sets_needs_clarification(monkeypatch):
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.intake.call_llm",
        _make_call_llm_sequence(_INTAKE_BAD_ZIP_JSON),
    )
    result = await run_intake("I live in Miami area", [], "unused.db")
    assert result.needs_clarification is True
    assert result.clarification_question


# ---------------------------------------------------------------------------
# Ballot resolver tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ballot_resolver_returns_error_event_on_mcp_failure(monkeypatch):
    def _fail(inp, db_path):
        return ToolError(
            error_code="CIVIC_UNAVAILABLE",
            message="API down",
            recoverable=True,
            fallback_source=None,
        )

    monkeypatch.setattr(
        "apps.api.orchestrator.stages.ballot_resolver.handle_get_ballot_by_address",
        _fail,
    )
    result = await run_ballot_resolver("session-1", "33101", None, "unused.db")
    assert isinstance(result, ErrorEvent)
    assert result.error_code == "CIVIC_UNAVAILABLE"
    assert result.session_id == "session-1"


# ---------------------------------------------------------------------------
# Measure analyst tests
# ---------------------------------------------------------------------------


def _patch_measure_mcp(monkeypatch):
    """Patch all 4 MCP handlers in measure_analyst to return ToolError stubs."""
    for name in [
        "handle_get_measure_detail",
        "handle_get_measure_text",
        "handle_parse_measure_text",
        "handle_search_news",
    ]:
        monkeypatch.setattr(
            f"apps.api.orchestrator.stages.measure_analyst.{name}",
            _noop_mcp,
        )


_MEASURE_SUMMARY = MeasureSummary(
    id="FL-2022-M1",
    type="constitutional_amendment",
    short_title="Amendment 1",
    full_title="Amendment 1 — Full Title",
)


@pytest.mark.asyncio
async def test_measure_analyst_retries_on_bad_json(monkeypatch):
    _patch_measure_mcp(monkeypatch)
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.measure_analyst.call_llm",
        _make_call_llm_sequence("not valid json {{{", _MEASURE_VALID_JSON),
    )
    result = await run_measure_analysis(_MEASURE_SUMMARY, ["housing"], "unused.db")
    assert isinstance(result, MeasureAnalysis)
    assert result.measure_id == "FL-2022-M1"


@pytest.mark.asyncio
async def test_measure_analyst_returns_none_after_3_failures(monkeypatch):
    _patch_measure_mcp(monkeypatch)
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.measure_analyst.call_llm",
        _make_call_llm_sequence("bad {", "still bad {", "also bad {"),
    )
    result = await run_measure_analysis(_MEASURE_SUMMARY, ["housing"], "unused.db")
    assert result is None


@pytest.mark.asyncio
async def test_measure_analyst_always_has_both_arguments(monkeypatch):
    _patch_measure_mcp(monkeypatch)
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.measure_analyst.call_llm",
        _make_call_llm_sequence(_MEASURE_VALID_JSON),
    )
    result = await run_measure_analysis(_MEASURE_SUMMARY, ["economy"], "unused.db")
    assert result is not None
    assert result.proponent_argument
    assert result.opponent_argument


# ---------------------------------------------------------------------------
# Candidate analyst tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_analyst_assembles_race_from_candidates(monkeypatch):
    for name in ["handle_get_candidate_detail", "handle_get_campaign_finance", "handle_search_news"]:
        monkeypatch.setattr(
            f"apps.api.orchestrator.stages.candidate_analyst.{name}",
            _noop_mcp,
        )
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.candidate_analyst.call_llm",
        _make_call_llm_sequence(_CANDIDATE_VALID_JSON, _CANDIDATE_VALID_JSON),
    )
    race = RaceSummary(
        id="R-GOV",
        type="governor",
        title="Governor",
        candidate_ids=["C-1", "C-2"],
    )
    result = await run_candidate_analysis(race, ["housing"], "unused.db")
    assert isinstance(result, RaceAnalysis)
    assert len(result.candidates) == 2
    assert result.race_id == "R-GOV"


# ---------------------------------------------------------------------------
# Relevance ranker tests
# ---------------------------------------------------------------------------


def _make_measure(measure_id: str) -> MeasureAnalysis:
    return MeasureAnalysis(
        measure_id=measure_id,
        short_title=f"Amendment {measure_id[-1]}",
        plain_english_summary="A ballot measure.",
        what_yes_means="Yes does X.",
        what_no_means="No does Y.",
        fiscal_impact=None,
        fiscal_impact_source=None,
        proponent_argument="Proponents say yes.",
        opponent_argument="Opponents say no.",
        proponent_source="https://pro.example.com",
        opponent_source="https://con.example.com",
        topic_tags=["economy"],
        data_completeness="full",
        sources=[SourceCitation(
            name="Test", url="https://example.com",
            bias_rating=None, fetched_at="2026-01-01T00:00:00Z",
        )],
    )


@pytest.mark.asyncio
async def test_relevance_ranker_removes_outcome_preference_language(monkeypatch):
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.relevance_ranker.call_llm",
        _make_call_llm_sequence(_SCORES_WITH_FORBIDDEN),
    )
    measures = [_make_measure("FL-2022-M1")]
    result = await run_relevance_ranking(measures, [], ["housing"])
    assert result[0].relevance_reason == "[relevance reason unavailable]"


@pytest.mark.asyncio
async def test_relevance_ranker_sorts_by_score_descending(monkeypatch):
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.relevance_ranker.call_llm",
        _make_call_llm_sequence(_SCORES_JSON_UNSORTED),
    )
    measures = [_make_measure("FL-2022-M1"), _make_measure("FL-2022-M2")]
    result = await run_relevance_ranking(measures, [], ["housing", "taxes"])
    scores = [r.relevance_score for r in result]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Report assembler tests (sync — no mocks needed)
# ---------------------------------------------------------------------------


def _make_election() -> ElectionSummary:
    return ElectionSummary(id="FL-2022-GEN", name="2022 FL General", date="2022-11-08", state="FL")


def _make_precinct() -> PrecinctInfo:
    return PrecinctInfo(county="Miami-Dade", district=None, precinct_id=None)


def test_report_assembler_is_pure_function():
    """assemble_report must be synchronous and return BallotReport directly."""
    result = assemble_report(
        session_id="s-1",
        election=_make_election(),
        precinct=_make_precinct(),
        user_priorities=["housing"],
        measures=[],
        races=[],
        scores=[],
    )
    # Must not be a coroutine
    assert not inspect.iscoroutine(result)
    assert isinstance(result, BallotReport)
    assert result.session_id == "s-1"


def test_report_assembler_items_ordered_by_score():
    """BallotReport.items must be sorted by relevance_score descending."""
    m1 = _make_measure("FL-2022-M1")
    m2 = _make_measure("FL-2022-M2")
    scores = [
        RelevanceScore(
            item_id="FL-2022-M1", item_type="measure",
            relevance_score=3, relevance_reason="Low relevance.", matched_priorities=[],
        ),
        RelevanceScore(
            item_id="FL-2022-M2", item_type="measure",
            relevance_score=9, relevance_reason="High relevance.", matched_priorities=["economy"],
        ),
    ]
    report = assemble_report(
        session_id="s-2",
        election=_make_election(),
        precinct=_make_precinct(),
        user_priorities=["economy"],
        measures=[m1, m2],
        races=[],
        scores=scores,
    )
    assert len(report.items) == 2
    assert report.items[0].relevance_score >= report.items[1].relevance_score
    assert report.items[0].relevance_score == 9


# ---------------------------------------------------------------------------
# Slice 5: response_schema forwarding tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intake_passes_schema_to_call_llm(monkeypatch):
    """intake.py must forward response_schema=IntakeResult to call_llm."""
    captured = {}

    async def _capture_call_llm(*args, **kwargs):
        captured["response_schema"] = kwargs.get("response_schema")
        return _INTAKE_VALID_JSON

    monkeypatch.setattr("apps.api.orchestrator.stages.intake.call_llm", _capture_call_llm)
    await run_intake("I care about housing in Miami 33101", [], "unused.db")
    assert captured.get("response_schema") is IntakeResult


@pytest.mark.asyncio
async def test_measure_analyst_passes_schema_to_call_llm(monkeypatch):
    """measure_analyst.py must forward response_schema=MeasureAnalysis and max_tokens=2000."""
    _patch_measure_mcp(monkeypatch)
    captured = {}

    async def _capture_call_llm(*args, **kwargs):
        captured["response_schema"] = kwargs.get("response_schema")
        captured["max_tokens"] = kwargs.get("max_tokens")
        return _MEASURE_VALID_JSON

    monkeypatch.setattr("apps.api.orchestrator.stages.measure_analyst.call_llm", _capture_call_llm)
    await run_measure_analysis(_MEASURE_SUMMARY, ["economy"], "unused.db")
    assert captured.get("response_schema") is MeasureAnalysis
    assert captured.get("max_tokens") == 2000, (
        "max_tokens must be 2000 to handle FL-2024 amendment text length"
    )


@pytest.mark.asyncio
async def test_candidate_analyst_passes_schema_to_call_llm(monkeypatch):
    """candidate_analyst.py must forward response_schema=CandidateAnalysis to call_llm."""
    for name in ["handle_get_candidate_detail", "handle_get_campaign_finance", "handle_search_news"]:
        monkeypatch.setattr(
            f"apps.api.orchestrator.stages.candidate_analyst.{name}", _noop_mcp
        )
    captured = {}

    async def _capture_call_llm(*args, **kwargs):
        captured["response_schema"] = kwargs.get("response_schema")
        return _CANDIDATE_VALID_JSON

    monkeypatch.setattr("apps.api.orchestrator.stages.candidate_analyst.call_llm", _capture_call_llm)
    race = RaceSummary(id="R-GOV", type="governor", title="Governor", candidate_ids=["C-1"])
    await run_candidate_analysis(race, ["housing"], "unused.db")
    assert captured.get("response_schema") is CandidateAnalysis


@pytest.mark.asyncio
async def test_relevance_ranker_passes_schema_to_call_llm(monkeypatch):
    """relevance_ranker.py must forward response_schema=RelevanceRanking to call_llm."""
    captured = {}

    async def _capture_call_llm(*args, **kwargs):
        captured["response_schema"] = kwargs.get("response_schema")
        return _SCORES_JSON_UNSORTED

    monkeypatch.setattr("apps.api.orchestrator.stages.relevance_ranker.call_llm", _capture_call_llm)
    await run_relevance_ranking([_make_measure("FL-2022-M1")], [], ["housing"])
    assert captured.get("response_schema") is RelevanceRanking


@pytest.mark.asyncio
async def test_relevance_ranker_retry_still_fires_on_bad_json(monkeypatch):
    """Schema validation failure triggers retry; valid response on retry succeeds."""
    monkeypatch.setattr(
        "apps.api.orchestrator.stages.relevance_ranker.call_llm",
        _make_call_llm_sequence("not valid json {{{", _SCORES_JSON_UNSORTED),
    )
    measures = [_make_measure("FL-2022-M1"), _make_measure("FL-2022-M2")]
    result = await run_relevance_ranking(measures, [], ["housing", "taxes"])
    assert len(result) > 0
    scores = [r.relevance_score for r in result]
    assert scores == sorted(scores, reverse=True)
