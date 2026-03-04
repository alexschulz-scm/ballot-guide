"""
Centralized mock mode resolution for MCP server source clients.

Two-tier hierarchy:
1. ``MOCK_EXTERNAL_APIS=true`` — master override, mocks ALL sources.
2. ``MOCK_<SOURCE>=true``     — per-source flag, checked only when
   the master override is *not* set.

Usage in source clients::

    from mcp_servers.shared.mock_config import is_mock_mode

    if is_mock_mode("MOCK_CIVIC_API"):
        return MOCK_CIVIC_RESPONSE
"""

import os


def is_mock_mode(source_flag: str) -> bool:
    """
    Return True if the given source should be mocked.

    Checks the master ``MOCK_EXTERNAL_APIS`` first (backwards-compatible).
    Falls back to the per-source flag (e.g. ``MOCK_CIVIC_API``).
    """
    if os.environ.get("MOCK_EXTERNAL_APIS", "false").lower() == "true":
        return True
    return os.environ.get(source_flag, "false").lower() == "true"
