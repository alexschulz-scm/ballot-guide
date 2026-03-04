"""
news-mcp MCP server entry point.

Registers two tools with the MCP framework and runs on stdio transport:
  - search_news
  - get_source_bias

Run as: python -m mcp_servers.news.server
"""

import asyncio
import os

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from mcp_servers.news.tools.bias import handle_get_source_bias
from mcp_servers.news.tools.search import handle_search_news
from mcp_servers.shared.models import (
    GetSourceBiasInput,
    SearchNewsInput,
    ToolError,
)

DB_PATH: str = os.environ.get("DB_PATH", "/data/ballot-guide.db")

server = Server("news-mcp")

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_news": (
        "Search for recent news articles about a ballot measure or candidate. "
        "Returns articles enriched with media bias ratings."
    ),
    "get_source_bias": (
        "Return the political bias rating for a news source domain. "
        "Always returns a result — unknown domains return found=false."
    ),
}

_TOOL_HANDLERS = {
    "search_news":      (SearchNewsInput,      lambda inp, db: handle_search_news(inp, db)),
    "get_source_bias":  (GetSourceBiasInput,   lambda inp, db: handle_get_source_bias(inp)),
}


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise all news-mcp tools to the MCP client."""
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
            message=f"Tool '{name}' is not registered in news-mcp",
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
