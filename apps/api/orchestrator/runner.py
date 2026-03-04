"""
Orchestrator runner — entry point that sequences all 5 stages.

The API layer calls ``run_orchestrator()`` and iterates the async generator
to obtain ``OrchestratorEvent`` objects which it streams as SSE.

Key responsibilities:
- Sequence stages in order (intake → ballot → analysis → ranking → report)
- Yield events for the API layer to stream
- Write session state via session/store.py (cross-layer rule)
- Convert MCP types to orchestrator types where needed

NOT responsible for:
- DoneEvent (router's ``finally`` block)
- Session status management (router sets processing/active/error)
- HTTP concerns (headers, streaming format)
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from apps.api.db.versioning import _compute_current_data_version
from apps.api.orchestrator.events import (
    ClarificationNeededEvent,
    ErrorEvent,
    IntakeCompleteEvent,
    ItemAnalyzedEvent,
    OrchestratorEvent,
    RankingCompleteEvent,
    ReportCompleteEvent,
)
from apps.api.orchestrator.schemas import (
    ElectionSummary,
    MeasureAnalysis,
    PrecinctInfo,
    RaceAnalysis,
)
from apps.api.orchestrator.stages.ballot_resolver import (
    BallotResolverResult,
    run_ballot_resolver,
)
from apps.api.orchestrator.stages.candidate_analyst import run_candidate_analysis
from apps.api.orchestrator.stages.follow_up import run_follow_up
from apps.api.orchestrator.stages.intake import run_intake
from apps.api.orchestrator.stages.measure_analyst import run_measure_analysis
from apps.api.orchestrator.stages.relevance_ranker import run_relevance_ranking
from apps.api.orchestrator.stages.report_assembler import assemble_report
from apps.api.session.store import (
    get_session,
    load_messages,
    save_report,
    update_session_after_ballot,
    update_session_after_intake,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_orchestrator(
    session_id: str,
    message: str,
    db_path: str,
) -> AsyncGenerator[OrchestratorEvent, None]:
    """Sequences all 5 orchestrator stages. Yields events for SSE streaming."""
    history = await load_messages(session_id, db_path)

    # Follow-up mode: if session already has a report, answer conversationally
    session = await get_session(session_id, db_path)
    if session and session.get("report_json"):
        response = await run_follow_up(
            message, history, session["report_json"],
        )
        yield ClarificationNeededEvent(
            event_type="clarification_needed",
            session_id=session_id,
            timestamp=_now_iso(),
            question=response,
        )
        return

    # Stage 1: Intake
    intake = await run_intake(message, history, db_path)
    if intake.needs_clarification:
        yield ClarificationNeededEvent(
            event_type="clarification_needed",
            session_id=session_id,
            timestamp=_now_iso(),
            question=intake.clarification_question or "Could you provide more details?",
        )
        return

    yield _intake_complete_event(session_id, intake)
    await update_session_after_intake(
        session_id, intake.zip_code, intake.priorities,
        intake.priorities_raw, intake.display_name, db_path,
    )

    # Stage 2: Ballot Resolution
    ballot_data = await _resolve_ballot(session_id, intake.zip_code, db_path)
    if isinstance(ballot_data, ErrorEvent):
        yield ballot_data
        return

    yield ballot_data["event"]
    ballot = ballot_data["ballot"]

    # Stages 3-5: Analyze, rank, assemble
    async for event in _analyze_rank_report(
        session_id, ballot, intake.priorities, ballot_data["data_version"], db_path,
    ):
        yield event


def _intake_complete_event(session_id, intake):
    """Build IntakeCompleteEvent from intake result."""
    return IntakeCompleteEvent(
        event_type="intake_complete",
        session_id=session_id,
        timestamp=_now_iso(),
        zip_code=intake.zip_code,
        priorities=intake.priorities,
        display_name=intake.display_name,
    )


async def _resolve_ballot(session_id, zip_code, db_path):
    """Run ballot resolver. Returns dict with event/ballot/data_version, or ErrorEvent."""
    session = await get_session(session_id, db_path)
    pre_selected_election = session["ballot_id"] if session else None
    logger.info(
        "Ballot resolve: session=%s, zip=%s, pre_selected=%s",
        session_id, zip_code, pre_selected_election,
    )
    result = await run_ballot_resolver(session_id, zip_code, pre_selected_election, db_path)
    if isinstance(result, ErrorEvent):
        return result

    ballot = result.ballot
    election_id = ballot.election.id
    await update_session_after_ballot(session_id, election_id, db_path)
    data_version = await _compute_current_data_version(election_id, db_path)

    return {"event": result.event, "ballot": ballot, "data_version": data_version}


async def _analyze_ballot_items(session_id, ballot, priorities, db_path):
    """Analyze each ballot item. Yields ItemAnalyzedEvent for each."""
    measures: list[MeasureAnalysis] = []
    races: list[RaceAnalysis] = []
    items_total = len(ballot.measures) + len(ballot.races)
    items_complete = 0

    for ms in ballot.measures:
        analysis = await run_measure_analysis(ms, priorities, db_path)
        items_complete += 1
        if analysis is not None:
            measures.append(analysis)
        yield ItemAnalyzedEvent(
            event_type="item_analyzed", session_id=session_id,
            timestamp=_now_iso(), item_id=ms.id,
            item_title=ms.short_title,
            items_complete=items_complete, items_total=items_total,
        )

    for race in ballot.races:
        analysis = await run_candidate_analysis(race, priorities, db_path)
        items_complete += 1
        if analysis is not None:
            races.append(analysis)
        yield ItemAnalyzedEvent(
            event_type="item_analyzed", session_id=session_id,
            timestamp=_now_iso(), item_id=race.id,
            item_title=race.title,
            items_complete=items_complete, items_total=items_total,
        )

    # Attach results for caller to access after iteration
    yield measures, races


async def _analyze_rank_report(session_id, ballot, priorities, data_version, db_path):
    """Stages 3-5: analyze items, rank, assemble report."""
    election = ElectionSummary.model_validate(ballot.election.model_dump())
    precinct = PrecinctInfo.model_validate(ballot.precinct.model_dump())

    # Stage 3: analyze each item
    measures = []
    races = []
    async for item in _analyze_ballot_items(session_id, ballot, priorities, db_path):
        if isinstance(item, tuple):
            measures, races = item
        else:
            yield item

    # Stage 4: relevance ranking
    scores = await run_relevance_ranking(measures, races, priorities)
    top_title = _find_item_title(
        scores[0].item_id if scores else "", measures, races,
    )
    yield RankingCompleteEvent(
        event_type="ranking_complete", session_id=session_id,
        timestamp=_now_iso(), top_item_title=top_title,
    )

    # Stage 5: report assembly
    report = assemble_report(
        session_id, election, precinct, priorities, measures, races, scores,
    )
    yield ReportCompleteEvent(
        event_type="report_complete", session_id=session_id,
        timestamp=_now_iso(), report=report,
    )
    await save_report(session_id, report.model_dump_json(), data_version, db_path)


def _find_item_title(
    item_id: str,
    measures: list[MeasureAnalysis],
    races: list[RaceAnalysis],
) -> str:
    """Look up item title by ID across measures and races."""
    for m in measures:
        if m.measure_id == item_id:
            return m.short_title
    for r in races:
        if r.race_id == item_id:
            return r.race_title
    return item_id or "N/A"
