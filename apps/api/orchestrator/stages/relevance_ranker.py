"""
Stage 4: Relevance Ranker — score all ballot items against user priorities.
"""
import json
import logging

from apps.api.orchestrator.llm_client import (
    SchemaValidationError,
    call_llm,
    load_prompt,
    parse_json_response,
)
from apps.api.orchestrator.schemas import MeasureAnalysis, RaceAnalysis, RelevanceRanking, RelevanceScore

logger = logging.getLogger(__name__)

_FORBIDDEN_PHRASES: frozenset[str] = frozenset({
    "help you",
    "benefit you",
    "support your goal",
    "align with your values",
    "better for you",
    "improve your",
})


def _scrub_scores(scores: list[RelevanceScore]) -> list[RelevanceScore]:
    """Scrub forbidden phrases and sort by relevance descending."""
    scrubbed = [
        score.model_copy(update={
            "relevance_reason": _scrub_reason(score.relevance_reason, score.item_id)
        })
        for score in scores
    ]
    return sorted(scrubbed, key=lambda s: s.relevance_score, reverse=True)


async def run_relevance_ranking(
    measures: list[MeasureAnalysis],
    races: list[RaceAnalysis],
    user_priorities: list[str],
) -> list[RelevanceScore]:
    """Score all ballot items against user priorities. Retries up to 3x."""
    system_prompt = load_prompt("system")
    formatted = (
        load_prompt("relevance_ranking")
        .replace("{priorities}", ", ".join(user_priorities))
        .replace("{items_json}", _build_items_json(measures, races))
    )
    messages = [{"role": "user", "content": formatted}]
    response = ""

    for attempt in range(3):
        try:
            response = await call_llm(
                system_prompt, messages, max_tokens=800, response_schema=RelevanceRanking
            )
            parsed = await parse_json_response(response, RelevanceRanking)
            return _scrub_scores(parsed.scores)
        except SchemaValidationError as exc:
            if attempt == 2:
                logger.error("All retries failed for relevance ranking: %s", exc)
                return []
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"Your response had this error: {exc}. Return valid JSON.",
            })
    return []


def _build_items_json(measures: list[MeasureAnalysis], races: list[RaceAnalysis]) -> str:
    """Build a compact JSON summary of all ballot items for the ranking prompt."""
    items = [
        {"id": m.measure_id, "type": "measure", "title": m.short_title, "topic_tags": m.topic_tags}
        for m in measures
    ]
    items += [
        {"id": r.race_id, "type": "race", "title": r.race_title, "topic_tags": []}
        for r in races
    ]
    return json.dumps(items)


def _scrub_reason(reason: str, item_id: str) -> str:
    """Replace relevance_reason containing forbidden phrases with a safe placeholder."""
    lower = reason.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lower:
            logger.warning(
                "Forbidden phrase %r in relevance_reason for %s — replacing", phrase, item_id
            )
            return "[relevance reason unavailable]"
    return reason
