"""
Configuration constants for the news-mcp server.

All TTL values and API URLs are defined here. Never hardcode these values
inline in tool handlers or source clients.
"""

# Cache TTL values (in seconds)
NEWS_CACHE_TTL_SECONDS: int = 3600  # 1 hour

# External API base URLs
NEWSAPI_URL: str = "https://newsapi.org/v2/everything"
