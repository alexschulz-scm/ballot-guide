"""
NewsAPI client for news search.

Fetches news articles from NewsAPI.org. Checks MOCK_EXTERNAL_APIS before
making any real HTTP calls. Returns raw NewsAPI response dicts.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from mcp_servers.news.constants import NEWSAPI_URL
from mcp_servers.shared.mock_config import is_mock_mode

# ---------------------------------------------------------------------------
# Mock data — returned when MOCK_EXTERNAL_APIS=true
# ---------------------------------------------------------------------------

MOCK_NEWSAPI_RESPONSE: dict = {
    "status": "ok",
    "totalResults": 2,
    "articles": [
        {
            "source": {"id": "miami-herald", "name": "Miami Herald"},
            "title": "Florida Amendment 2 Passes with 60% Vote",
            "url": "https://miamiherald.com/news/politics/florida-amendment-2-passes",
            "publishedAt": "2022-11-09T00:00:00Z",
            "description": "Florida voters approved Amendment 2 raising the minimum wage to $15 per hour.",
        },
        {
            "source": {"id": None, "name": "Example Unknown News"},
            "title": "Florida Election Results 2022",
            "url": "https://example-unknown.com/fl-results-2022",
            "publishedAt": "2022-11-09T00:00:00Z",
            "description": "Summary of Florida 2022 election results.",
        },
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_news(
    query: str,
    api_key: str,
    date_from: str | None,
    date_to: str | None,
    max_results: int,
) -> dict:
    """
    Return the NewsAPI response dict for the given query.

    Raises ValueError("NEWSAPI_UNAVAILABLE") on any HTTP or parse error.
    """
    if is_mock_mode("MOCK_NEWSAPI"):
        return MOCK_NEWSAPI_RESPONSE

    url = _build_newsapi_url(query, api_key, date_from, date_to, max_results)
    return _make_newsapi_request(url)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_newsapi_url(
    query: str,
    api_key: str,
    date_from: str | None,
    date_to: str | None,
    max_results: int,
) -> str:
    """Construct the NewsAPI request URL with all parameters."""
    params: dict[str, str] = {
        "q": query,
        "apiKey": api_key,
        "pageSize": str(min(max_results, 100)),
        "language": "en",
        "sortBy": "publishedAt",
    }
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    return f"{NEWSAPI_URL}?{urllib.parse.urlencode(params)}"


def _make_newsapi_request(url: str) -> dict:
    """Make a GET request to NewsAPI and return the parsed JSON body."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ballot-guide/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ValueError("NEWSAPI_UNAVAILABLE: rate limited") from exc
        raise ValueError(f"NEWSAPI_UNAVAILABLE: HTTP {exc.code}") from exc
    except Exception as exc:
        raise ValueError(f"NEWSAPI_UNAVAILABLE: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("NEWSAPI_UNAVAILABLE: invalid JSON response") from exc
