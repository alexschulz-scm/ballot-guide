"""
Tests for orchestrator schemas and events.

All tests are pure Pydantic validation — no db_path, no mock_env, no HTTP.
Tests run offline and do not depend on any external state.
"""

import pytest
from typing import Literal, get_type_hints, get_args, get_origin

from pydantic import ValidationError

from apps.api.orchestrator.events import (
    BallotFoundEvent,
    ClarificationNeededEvent,
    DoneEvent,
    ErrorEvent,
    IntakeCompleteEvent,
    ItemAnalyzedEvent,
    RankingCompleteEvent,
    ReportCompleteEvent,
)
from apps.api.orchestrator.schemas import (
    BallotReport,
    BallotReportItem,
    CandidateAnalysis,
    ElectionSummary,
    IntakeResult,
    MeasureAnalysis,
    PrecinctInfo,
    RaceAnalysis,
    RelevanceScore,
    SourceCitation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source() -> SourceCitation:
    return SourceCitation(
        name="Ballotpedia",
        url="https://ballotpedia.org/test",
        bias_rating=None,
        fetched_at="2026-01-01T00:00:00Z",
    )


def _make_measure_analysis(**overrides) -> dict:
    defaults = dict(
        measure_id="FL-2022-M1",
        short_title="Amendment 1",
        plain_english_summary="A test summary.",
        what_yes_means="Yes means A.",
        what_no_means="No means B.",
        fiscal_impact=None,
        fiscal_impact_source=None,
        proponent_argument="For argument.",
        opponent_argument="Against argument.",
        proponent_source="https://example.com/pro",
        opponent_source="https://example.com/con",
        topic_tags=["housing"],
        data_completeness="full",
        sources=[_make_source().model_dump()],
    )
    defaults.update(overrides)
    return defaults


def _make_election() -> ElectionSummary:
    return ElectionSummary(id="FL-2022-GEN", name="2022 Florida General", date="2022-11-08", state="FL")


def _make_precinct() -> PrecinctInfo:
    return PrecinctInfo(county="Miami-Dade", district=None, precinct_id=None)


# ---------------------------------------------------------------------------
# Test 1: IntakeResult rejects unknown priority topics
# ---------------------------------------------------------------------------


def test_intake_result_rejects_unknown_priority_topic():
    """Non-taxonomy priority values are silently filtered out."""
    result = IntakeResult(
        zip_code="33101",
        address_full=None,
        priorities=["unknown_topic", "another_fake_priority"],
        priorities_raw="unknown topic and another fake",
        display_name=None,
        needs_clarification=False,
        clarification_question=None,
    )
    assert result.priorities == []


# ---------------------------------------------------------------------------
# Test 2: IntakeResult enforces max 5 priorities
# ---------------------------------------------------------------------------


def test_intake_result_max_5_priorities_enforced():
    """6 valid taxonomy values are silently truncated to 5."""
    six_topics = [
        "housing", "education", "taxes", "healthcare", "environment", "economy"
    ]
    result = IntakeResult(
        zip_code="33101",
        address_full=None,
        priorities=six_topics,
        priorities_raw="all of them",
        display_name=None,
        needs_clarification=False,
        clarification_question=None,
    )
    assert len(result.priorities) == 5
    assert result.priorities == six_topics[:5]


# ---------------------------------------------------------------------------
# Test 3: MeasureAnalysis requires at least one source
# ---------------------------------------------------------------------------


def test_measure_analysis_requires_sources():
    """sources=[] raises ValidationError."""
    data = _make_measure_analysis(sources=[])
    with pytest.raises(ValidationError):
        MeasureAnalysis.model_validate(data)


# ---------------------------------------------------------------------------
# Test 4: BallotReport has no forbidden recommendation fields
# ---------------------------------------------------------------------------


def test_ballot_report_has_no_recommendation_field():
    """BallotReport must not have any forbidden neutrality-violating fields."""
    forbidden = {
        "recommendation",
        "suggested_vote",
        "lean",
        "preferred_candidate",
        "vote_for",
    }
    report_fields = set(BallotReport.model_fields.keys())
    found = forbidden & report_fields
    assert found == set(), f"Forbidden fields found in BallotReport: {found}"


# ---------------------------------------------------------------------------
# Test 5: RelevanceScore accepts 1-10, rejects outside range
# ---------------------------------------------------------------------------


def test_relevance_score_is_1_to_10():
    """relevance_score must be 1-10 inclusive."""
    valid = RelevanceScore(
        item_id="FL-2022-M1",
        item_type="measure",
        relevance_score=5,
        relevance_reason="This measure affects housing regulations.",
        matched_priorities=["housing"],
    )
    assert valid.relevance_score == 5

    with pytest.raises(ValidationError):
        RelevanceScore(
            item_id="FL-2022-M1",
            item_type="measure",
            relevance_score=0,
            relevance_reason="Too low.",
            matched_priorities=[],
        )

    with pytest.raises(ValidationError):
        RelevanceScore(
            item_id="FL-2022-M1",
            item_type="measure",
            relevance_score=11,
            relevance_reason="Too high.",
            matched_priorities=[],
        )


# ---------------------------------------------------------------------------
# Test 6: SourceCitation requires url field
# ---------------------------------------------------------------------------


def test_source_citation_requires_url():
    """Missing url field raises ValidationError."""
    with pytest.raises(ValidationError):
        SourceCitation(
            name="Ballotpedia",
            bias_rating=None,
            fetched_at="2026-01-01T00:00:00Z",
            # url is missing
        )


# ---------------------------------------------------------------------------
# Test 7: All event classes have event_type as a Literal annotation
# ---------------------------------------------------------------------------


def test_all_events_have_event_type_literal():
    """Each of the 8 concrete event classes annotates event_type with Literal."""
    event_classes = [
        IntakeCompleteEvent,
        ClarificationNeededEvent,
        BallotFoundEvent,
        ItemAnalyzedEvent,
        RankingCompleteEvent,
        ReportCompleteEvent,
        ErrorEvent,
        DoneEvent,
    ]

    for cls in event_classes:
        hints = get_type_hints(cls)
        assert "event_type" in hints, f"{cls.__name__} missing event_type annotation"
        annotation = hints["event_type"]
        origin = get_origin(annotation)
        assert origin is Literal, (
            f"{cls.__name__}.event_type is {annotation!r}, expected Literal[...]"
        )


# ---------------------------------------------------------------------------
# Test 8: ReportCompleteEvent.report field is typed as BallotReport
# ---------------------------------------------------------------------------


def test_report_complete_event_contains_ballot_report():
    """ReportCompleteEvent.report annotation is BallotReport."""
    hints = get_type_hints(ReportCompleteEvent)
    assert hints.get("report") is BallotReport, (
        f"ReportCompleteEvent.report expected BallotReport, got {hints.get('report')}"
    )
