"""
Tool handler: search_news

Searches for news articles via NewsAPI, enriches each article with
bias ratings, and caches results in SQLite.
"""

import os
from urllib.parse import urlparse

from mcp_servers.news.constants import NEWS_CACHE_TTL_SECONDS
from mcp_servers.news.sources.newsapi import fetch_news
from mcp_servers.news.tools.bias import handle_get_source_bias
from mcp_servers.shared.cache import get_cached, make_cache_key, set_cached
from mcp_servers.shared.mock_config import is_mock_mode
from mcp_servers.shared.models import (
    GetSourceBiasInput,
    NewsArticle,
    NewsSearchResult,
    SearchNewsInput,
    ToolError,
)


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------


def handle_search_news(
    inp: SearchNewsInput, db_path: str
) -> NewsSearchResult | ToolError:
    """Return news articles for a query, enriched with bias ratings."""
    cache_key = make_cache_key(
        "news", inp.query.lower(), inp.date_from or "", inp.date_to or ""
    )

    cached = get_cached(cache_key, db_path)
    if cached is not None:
        return NewsSearchResult.model_validate({**cached, "cache_hit": True})

    api_key = os.environ.get("NEWSAPI_KEY", "")

    if not api_key and not is_mock_mode("MOCK_NEWSAPI"):
        return ToolError(
            error_code="NEWSAPI_UNAVAILABLE",
            message="NEWSAPI_KEY environment variable not set",
            recoverable=False,
            fallback_source=None,
        )

    try:
        raw = fetch_news(inp.query, api_key, inp.date_from, inp.date_to, inp.max_results)
    except ValueError as exc:
        return ToolError(
            error_code="NEWSAPI_UNAVAILABLE",
            message=str(exc),
            recoverable=True,
            fallback_source=None,
        )

    articles = _build_articles_with_bias(raw.get("articles", []))
    result = NewsSearchResult(articles=articles, query_used=inp.query, cache_hit=False)
    set_cached(cache_key, result.model_dump(), NEWS_CACHE_TTL_SECONDS, "newsapi", db_path)
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_articles_with_bias(raw_articles: list) -> list[NewsArticle]:
    """Enrich each raw article dict with bias rating lookup."""
    articles = []
    for raw in raw_articles:
        domain = _extract_domain(raw.get("url", ""))
        bias = handle_get_source_bias(GetSourceBiasInput(domain=domain))
        articles.append(_build_article(raw, bias))
    return articles


def _extract_domain(url: str) -> str:
    """Extract bare domain (no www.) from a URL. Returns '' on failure."""
    try:
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return ""


def _build_article(raw: dict, bias) -> NewsArticle:
    """Construct a NewsArticle from raw NewsAPI dict and bias rating."""
    source = raw.get("source") or {}
    description = raw.get("description")
    if description and len(description) > 300:
        description = description[:297] + "..."
    return NewsArticle(
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        source_name=source.get("name", ""),
        published_at=raw.get("publishedAt", ""),
        description=description,
        bias_rating=bias.bias_rating if bias.found else None,
        bias_source=bias.bias_source if bias.found else None,
    )
