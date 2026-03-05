"""
Orchestrator event stream models.

Every event yielded by run_orchestrator() is an OrchestratorEvent subclass.
The API layer converts these to SSE and streams them to the frontend.

Each subclass uses event_type: Literal[...] — not a free-form string.
This prevents typos in event type names from reaching the API layer.

Integration note (Issue 6): OrchestratorEvent base class has timestamp: str.
DoneEvent inherits it — the API spec SSE example confirmed timestamp is required
on the done event as well. No need to re-declare it in DoneEvent.
"""

from typing import Literal

from pydantic import BaseModel

from apps.api.orchestrator.schemas import BallotReport


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------


class OrchestratorEvent(BaseModel):
    """Base class for all orchestrator events."""

    event_type: str
    session_id: str
    timestamp: str   # ISO 8601 — present on all events including DoneEvent


# ---------------------------------------------------------------------------
# Stage events
# ---------------------------------------------------------------------------


class IntakeCompleteEvent(OrchestratorEvent):
    """Yielded after Stage 1 (Intake) completes successfully."""

    event_type: Literal["intake_complete"]
    zip_code: str
    priorities: list[str]
    display_name: str | None


class ClarificationNeededEvent(OrchestratorEvent):
    """Yielded when Stage 1 cannot extract zip/priorities. Run stops here."""

    event_type: Literal["clarification_needed"]
    question: str   # user-facing clarification question


class BallotFoundEvent(OrchestratorEvent):
    """Yielded after Stage 2 (Ballot Resolution) finds the ballot."""

    event_type: Literal["ballot_found"]
    election_name: str
    item_count: int   # total items on ballot
    message: str      # e.g. "Found your ballot — 12 items. Analyzing..."


class ItemAnalyzedEvent(OrchestratorEvent):
    """Yielded after each ballot item is analyzed in Stage 3."""

    event_type: Literal["item_analyzed"]
    item_id: str
    item_title: str
    items_complete: int   # how many items done so far
    items_total: int      # total items to analyze


class RankingCompleteEvent(OrchestratorEvent):
    """Yielded after Stage 4 (Relevance Ranking) completes."""

    event_type: Literal["ranking_complete"]
    top_item_title: str   # first item in ranked list (teaser for frontend)


class ReportCompleteEvent(OrchestratorEvent):
    """Yielded after Stage 5 (Report Assembly) completes. Contains full report."""

    event_type: Literal["report_complete"]
    report: BallotReport


class FollowUpResponseEvent(OrchestratorEvent):
    """Yielded when the follow-up handler answers a post-report question."""

    event_type: Literal["follow_up_response"]
    answer: str           # plain text / markdown response
    sources_used: list[str]   # MCP tools called, empty if report-only


class ErrorEvent(OrchestratorEvent):
    """Yielded when a stage encounters an unrecoverable error."""

    event_type: Literal["error"]
    error_code: str
    message: str      # user-facing message
    recoverable: bool


class DoneEvent(OrchestratorEvent):
    """
    Always the last event yielded — even after errors.
    timestamp inherited from OrchestratorEvent base class.
    """

    event_type: Literal["done"]
