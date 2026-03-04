"""
Configuration constants for the ballot_data MCP server.

All TTL values, caps, and domain constants are defined here.
Import from this module — never hardcode these values inline in tool
handlers or source clients.
"""

# Cache TTL values (in seconds)
BALLOT_CACHE_TTL_SECONDS: int = 21600     # 6 hours
MEASURE_CACHE_TTL_SECONDS: int = 43200    # 12 hours
CANDIDATE_CACHE_TTL_SECONDS: int = 21600  # 6 hours
FINANCE_CACHE_TTL_SECONDS: int = 86400    # 24 hours

# Response size caps
MAX_TOP_DONORS: int = 5

# Canonical topic taxonomy — must match CLAUDE.md and shared/models.py contracts
TOPIC_TAXONOMY: frozenset[str] = frozenset({
    "housing",
    "education",
    "taxes",
    "healthcare",
    "environment",
    "public_safety",
    "economy",
    "voting_rights",
    "infrastructure",
    "senior_services",
})

# Florida scope — MVP restriction
VALID_STATE_CODE: str = "FL"
