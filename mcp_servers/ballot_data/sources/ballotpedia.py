"""
Ballotpedia scraper / API client.

Fetches measure and candidate information from Ballotpedia pages.
Uses stdlib urllib and html.parser — no external dependencies.
Checks MOCK_EXTERNAL_APIS before any real HTTP calls.
"""

import urllib.error
import urllib.request
from html.parser import HTMLParser

from mcp_servers.shared.mock_config import is_mock_mode

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_BALLOTPEDIA_MEASURE: dict = {
    "summary": "This is a mock Ballotpedia measure summary for testing.",
    "full_text": "Mock full text of the measure.",
    "sources": [
        {
            "name": "Ballotpedia",
            "url": "https://ballotpedia.org/mock",
            "fetched_at": "2022-12-01T00:00:00",
            "bias_rating": None,
        }
    ],
}

MOCK_BALLOTPEDIA_CANDIDATE: dict = {
    "bio": "Mock candidate bio from Ballotpedia.",
    "photo_url": None,
    "website_url": None,
    "sources": [
        {
            "name": "Ballotpedia",
            "url": "https://ballotpedia.org/mock_candidate",
            "fetched_at": "2022-12-01T00:00:00",
            "bias_rating": None,
        }
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_measure_from_ballotpedia(ballotpedia_url: str) -> dict:
    """
    Fetch and parse a measure page from Ballotpedia.

    Returns a dict with summary, full_text, and sources.
    Raises ValueError("BALLOTPEDIA_UNAVAILABLE") on any failure.
    """
    if is_mock_mode("MOCK_BALLOTPEDIA_API"):
        return MOCK_BALLOTPEDIA_MEASURE

    html = _fetch_html(ballotpedia_url)
    return _parse_measure_html(html, ballotpedia_url)


def fetch_candidate_from_ballotpedia(ballotpedia_url: str) -> dict:
    """
    Fetch and parse a candidate page from Ballotpedia.

    Returns a dict with bio, photo_url, website_url, and sources.
    Raises ValueError("BALLOTPEDIA_UNAVAILABLE") on any failure.
    """
    if is_mock_mode("MOCK_BALLOTPEDIA_API"):
        return MOCK_BALLOTPEDIA_CANDIDATE

    html = _fetch_html(ballotpedia_url)
    return _parse_candidate_html(html, ballotpedia_url)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_html(url: str) -> str:
    """Fetch the raw HTML of a URL. Raises ValueError on any HTTP error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ballot-guide/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"BALLOTPEDIA_UNAVAILABLE: HTTP {exc.code}") from exc
    except Exception as exc:
        raise ValueError(f"BALLOTPEDIA_UNAVAILABLE: {exc}") from exc


def _parse_measure_html(html: str, source_url: str) -> dict:
    """Extract measure summary text from Ballotpedia HTML."""
    parser = _TextExtractor()
    parser.feed(html)
    summary = parser.get_text()[:1000] if parser.get_text() else None
    return {
        "summary": summary,
        "full_text": parser.get_text(),
        "sources": [_make_source(source_url)],
    }


def _parse_candidate_html(html: str, source_url: str) -> dict:
    """Extract candidate bio text from Ballotpedia HTML."""
    parser = _TextExtractor()
    parser.feed(html)
    bio = parser.get_text()[:500] if parser.get_text() else None
    return {
        "bio": bio,
        "photo_url": None,
        "website_url": None,
        "sources": [_make_source(source_url)],
    }


def _make_source(url: str) -> dict:
    """Build a SourceCitation-shaped dict for Ballotpedia."""
    from datetime import datetime, timezone
    return {
        "name": "Ballotpedia",
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "bias_rating": None,
    }


class _TextExtractor(HTMLParser):
    """Minimal HTML parser that collects visible text content."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)
