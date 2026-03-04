"""
Stage 5: Report Assembler — pure sync function that joins all data into BallotReport.

No Claude calls, no MCP calls, no async. This is deliberate: report assembly is
deterministic data joining. If you find yourself adding an external call here,
stop — that logic belongs in an earlier stage.
"""
from datetime import datetime, timezone

from apps.api.orchestrator.schemas import (
    BallotReport,
    BallotReportItem,
    ElectionSummary,
    MeasureAnalysis,
    PrecinctInfo,
    RaceAnalysis,
    RelevanceScore,
)


def assemble_report(
    session_id: str,
    election: ElectionSummary,
    precinct: PrecinctInfo,
    user_priorities: list[str],
    measures: list[MeasureAnalysis],
    races: list[RaceAnalysis],
    scores: list[RelevanceScore],
) -> BallotReport:
    """
    Joins measures/races with their RelevanceScore objects via item_id.
    Items not present in scores get relevance_score=0 and empty matched_priorities.
    Returns BallotReport with items sorted by relevance_score descending.
    """
    score_map = {s.item_id: s for s in scores}
    items = _build_items(measures, races, score_map)
    items.sort(key=lambda x: x.relevance_score, reverse=True)
    return BallotReport(
        session_id=session_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        election=election,
        precinct=precinct,
        user_priorities=user_priorities,
        items=items,
    )


def _build_items(
    measures: list[MeasureAnalysis],
    races: list[RaceAnalysis],
    score_map: dict[str, RelevanceScore],
) -> list[BallotReportItem]:
    """Convert measures and races into BallotReportItem objects."""
    items: list[BallotReportItem] = []
    for m in measures:
        score = score_map.get(m.measure_id)
        items.append(BallotReportItem(
            item_type="measure",
            relevance_score=score.relevance_score if score else 0,
            relevance_reason=score.relevance_reason if score else "",
            matched_priorities=score.matched_priorities if score else [],
            measure=m,
            race=None,
        ))
    for r in races:
        score = score_map.get(r.race_id)
        items.append(BallotReportItem(
            item_type="race",
            relevance_score=score.relevance_score if score else 0,
            relevance_reason=score.relevance_reason if score else "",
            matched_priorities=score.matched_priorities if score else [],
            measure=None,
            race=r,
        ))
    return items
