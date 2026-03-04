"""
ballot-data-mcp MCP server entry point.

Registers four tools with the MCP framework and runs on stdio transport:
  - get_ballot_by_address
  - get_measure_detail
  - get_candidate_detail
  - get_campaign_finance

Run as: python -m mcp_servers.ballot_data.server
"""

import asyncio
import os

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from mcp_servers.ballot_data.tools.ballot import handle_get_ballot_by_address
from mcp_servers.ballot_data.tools.candidate import handle_get_candidate_detail
from mcp_servers.ballot_data.tools.finance import handle_get_campaign_finance
from mcp_servers.ballot_data.tools.measure import handle_get_measure_detail
from mcp_servers.shared.models import (
    GetBallotByAddressInput,
    GetCampaignFinanceInput,
    GetCandidateDetailInput,
    GetMeasureDetailInput,
    ToolError,
)

DB_PATH: str = os.environ.get("DB_PATH", "/data/ballot-guide.db")

server = Server("ballot-data-mcp")

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_ballot_by_address": (
        "Return the full ballot for a Florida voter's address, including all races "
        "and ballot measures. Florida only."
    ),
    "get_measure_detail": (
        "Return the full structured profile of a ballot measure, including "
        "proponent and opponent arguments. Requires a measure_id."
    ),
    "get_candidate_detail": (
        "Return a candidate's full profile and stated positions on issues, "
        "optionally filtered to specific topics."
    ),
    "get_campaign_finance": (
        "Return a campaign finance summary for a candidate or measure, "
        "including top donors and total raised."
    ),
}

_TOOL_HANDLERS = {
    "get_ballot_by_address": (GetBallotByAddressInput, handle_get_ballot_by_address),
    "get_measure_detail": (GetMeasureDetailInput, handle_get_measure_detail),
    "get_candidate_detail": (GetCandidateDetailInput, handle_get_candidate_detail),
    "get_campaign_finance": (GetCampaignFinanceInput, handle_get_campaign_finance),
}


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise all ballot-data-mcp tools to the MCP client."""
    return [
        Tool(
            name=name,
            description=_TOOL_DESCRIPTIONS[name],
            inputSchema=inp_cls.model_json_schema(),
        )
        for name, (inp_cls, _) in _TOOL_HANDLERS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch a tool call and return the serialized result."""
    if name not in _TOOL_HANDLERS:
        error = ToolError(
            error_code="UNKNOWN_TOOL",
            message=f"Tool '{name}' is not registered in ballot-data-mcp",
            recoverable=False,
            fallback_source=None,
        )
        return [TextContent(type="text", text=error.model_dump_json())]

    inp_cls, handler = _TOOL_HANDLERS[name]
    try:
        inp = inp_cls.model_validate(arguments)
    except ValidationError as exc:
        error = ToolError(
            error_code="INVALID_INPUT",
            message=str(exc),
            recoverable=False,
            fallback_source=None,
        )
        return [TextContent(type="text", text=error.model_dump_json())]

    result = handler(inp, DB_PATH)
    return [TextContent(type="text", text=result.model_dump_json())]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    asyncio.run(mcp.server.stdio.stdio_server(server))
