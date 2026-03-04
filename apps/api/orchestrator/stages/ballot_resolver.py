"""
Stage 2: Ballot Resolver — resolve zip code to a ballot via MCP.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from apps.api.orchestrator.events import BallotFoundEvent, ErrorEvent
from mcp_servers.ballot_data.tools.ballot import handle_get_ballot_by_address
from mcp_servers.shared.models import BallotResponse, GetBallotByAddressInput, ToolError

logger = logging.getLogger(__name__)


@dataclass
class BallotResolverResult:
    """Successful ballot resolution — carries both the event and the raw ballot data."""

    event: BallotFoundEvent  # for the runner to yield
    ballot: BallotResponse   # measures + races for Stage 3


async def run_ballot_resolver(
    session_id: str,
    zip_code: str,
    election_id: str | None,
    db_path: str,
) -> BallotResolverResult | ErrorEvent:
    """
    Calls get_ballot_by_address MCP tool.
    Returns BallotResolverResult on success.
    Returns ErrorEvent on ToolError — never raises exceptions.
    session_id required to populate ErrorEvent fields.
    """
    inp = GetBallotByAddressInput(address=zip_code, election_id=election_id)
    result = handle_get_ballot_by_address(inp, db_path)

    if isinstance(result, ToolError):
        logger.error("Ballot resolution failed: %s — %s", result.error_code, result.message)
        return ErrorEvent(
            event_type="error",
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error_code=result.error_code,
            message=result.message,
            recoverable=result.recoverable,
        )

    item_count = len(result.measures) + len(result.races)
    event = BallotFoundEvent(
        event_type="ballot_found",
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        election_name=result.election.name,
        item_count=item_count,
        message=f"Found your ballot — {item_count} items. Analyzing...",
    )
    return BallotResolverResult(event=event, ballot=result)
