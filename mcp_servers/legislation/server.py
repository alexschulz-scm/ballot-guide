"""
legislation-mcp MCP server entry point.

Registers two tools with the MCP framework and runs on stdio transport:
  - get_measure_text
  - parse_measure_text

Run as: python -m mcp_servers.legislation.server
"""

import asyncio
import os

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from mcp_servers.legislation.tools.measure_text import handle_get_measure_text
from mcp_servers.legislation.tools.parse_text import handle_parse_measure_text
from mcp_servers.shared.models import (
    GetMeasureTextInput,
    ParseMeasureTextInput,
    ToolError,
)

DB_PATH: str = os.environ.get("DB_PATH", "/data/ballot-guide.db")

server = Server("legislation-mcp")

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_measure_text": (
        "Fetch the raw legal text of a Florida ballot measure from the FL Legislature "
        "website or SQLite cache. Returns full statutory text."
    ),
    "parse_measure_text": (
        "Parse raw ballot measure legal text into labeled sections (findings, provisions, "
        "fiscal_impact, effective_date, definitions, other). Pure deterministic function."
    ),
}

_TOOL_HANDLERS = {
    "get_measure_text":   (GetMeasureTextInput,   lambda inp, db: handle_get_measure_text(inp, db)),
    "parse_measure_text": (ParseMeasureTextInput, lambda inp, db: handle_parse_measure_text(inp)),
}


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise all legislation-mcp tools to the MCP client."""
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
            message=f"Tool '{name}' is not registered in legislation-mcp",
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
