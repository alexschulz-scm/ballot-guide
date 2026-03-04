"""
Configuration constants for the legislation-mcp server.

All TTL values and base URLs are defined here. Import from this module —
never hardcode these values inline in tool handlers or parser modules.
"""

# Cache TTL values (in seconds)
MEASURE_TEXT_CACHE_TTL_SECONDS: int = 604800  # 7 days

# External source base URLs
FL_ELECTIONS_BASE_URL: str = "https://dos.myflorida.com/elections/"
FL_LEGISLATURE_BASE_URL: str = "https://www.flsenate.gov/Session/Bill"
