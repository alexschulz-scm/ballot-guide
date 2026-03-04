"""
Tests for the news-mcp server tools.

All tests run offline — real NewsAPI calls are mocked via MOCK_EXTERNAL_APIS=true
or via the missing-key guard. Uses fixtures from conftest.py.
"""

import pytest

from mcp_servers.news.tools.bias import handle_get_source_bias
from mcp_servers.news.tools.search import handle_search_news
from mcp_servers.shared.models import (
    GetSourceBiasInput,
    NewsSearchResult,
    SearchNewsInput,
    SourceBiasRating,
    ToolError,
)


# ---------------------------------------------------------------------------
# Test 1: Known domain returns found=True with correct rating
# ---------------------------------------------------------------------------


def test_get_source_bias_known_domain():
    """miamiherald.com is in bias_ratings.json → found=True, rating=Center."""
    inp = GetSourceBiasInput(domain="miamiherald.com")
    result = handle_get_source_bias(inp)
    assert isinstance(result, SourceBiasRating)
    assert result.found is True
    assert result.bias_rating == "Center"


# ---------------------------------------------------------------------------
# Test 2: Unknown domain returns found=False, type is SourceBiasRating
# ---------------------------------------------------------------------------


def test_get_source_bias_unknown_domain():
    """Unknown domain returns SourceBiasRating(found=False) — never ToolError."""
    inp = GetSourceBiasInput(domain="unknown-xyz-news.com")
    result = handle_get_source_bias(inp)
    assert isinstance(result, SourceBiasRating)
    assert result.found is False
    assert result.bias_rating is None


# ---------------------------------------------------------------------------
# Test 3: search_news cache_hit=True on second call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_news_cache_hit(db_path, mock_env, monkeypatch):
    """Second call with same query returns cache_hit=True."""
    monkeypatch.setenv("NEWSAPI_KEY", "test_key_news")
    inp = SearchNewsInput(query="Florida Amendment 2 minimum wage")

    first = handle_search_news(inp, db_path)
    assert isinstance(first, NewsSearchResult), f"Expected NewsSearchResult, got: {first}"
    assert first.cache_hit is False

    second = handle_search_news(inp, db_path)
    assert isinstance(second, NewsSearchResult)
    assert second.cache_hit is True


# ---------------------------------------------------------------------------
# Test 4: Missing NEWSAPI_KEY without mock → ToolError NEWSAPI_UNAVAILABLE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_news_missing_api_key(db_path, monkeypatch):
    """Without mock mode and no NEWSAPI_KEY, returns ToolError."""
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)

    inp = SearchNewsInput(query="Florida ballot measures 2024")
    result = handle_search_news(inp, db_path)
    assert isinstance(result, ToolError)
    assert result.error_code == "NEWSAPI_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Test 5: Mock mode returns NewsSearchResult with articles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_news_mock_returns_articles(db_path, mock_env, monkeypatch):
    """MOCK_EXTERNAL_APIS=true returns NewsSearchResult with ≥1 articles."""
    monkeypatch.setenv("NEWSAPI_KEY", "test_key_news")
    inp = SearchNewsInput(query="Florida Amendment 2")
    result = handle_search_news(inp, db_path)
    assert isinstance(result, NewsSearchResult)
    assert len(result.articles) >= 1


# ---------------------------------------------------------------------------
# Test 6: Articles from known domains are enriched with bias rating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_news_articles_enriched_with_bias(db_path, mock_env, monkeypatch):
    """Mock article from miamiherald.com URL gets bias_rating=Center."""
    monkeypatch.setenv("NEWSAPI_KEY", "test_key_news")
    inp = SearchNewsInput(query="Florida Amendment 2")
    result = handle_search_news(inp, db_path)
    assert isinstance(result, NewsSearchResult)

    miami_articles = [a for a in result.articles if "miamiherald" in a.url]
    assert len(miami_articles) >= 1
    assert miami_articles[0].bias_rating == "Center"


# ---------------------------------------------------------------------------
# Test 7: Cache key normalizes query to lowercase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_news_cache_key_normalized(db_path, mock_env, monkeypatch):
    """Same query in different case hits cache on second call."""
    monkeypatch.setenv("NEWSAPI_KEY", "test_key_news")
    inp_lower = SearchNewsInput(query="florida amendment 2")
    inp_upper = SearchNewsInput(query="FLORIDA AMENDMENT 2")

    first = handle_search_news(inp_lower, db_path)
    assert isinstance(first, NewsSearchResult)
    assert first.cache_hit is False

    second = handle_search_news(inp_upper, db_path)
    assert isinstance(second, NewsSearchResult)
    assert second.cache_hit is True
