"""
Tests for MCP source clients: openfec, fl_finance, newsapi, ballotpedia.

All HTTP calls are monkeypatched — no real network access.
"""

import io
import json
import urllib.error

import pytest

from mcp_servers.ballot_data.sources.ballotpedia import (
    _TextExtractor,
    _parse_candidate_html,
    _parse_measure_html,
    fetch_candidate_from_ballotpedia,
    fetch_measure_from_ballotpedia,
)
from mcp_servers.ballot_data.sources.fl_finance import (
    _parse_csv,
    _safe_float,
    fetch_fl_finance,
)
from mcp_servers.ballot_data.sources.openfec import (
    _map_entity_type,
    _make_request,
    fetch_openfec_finance,
)
from mcp_servers.news.sources.newsapi import (
    _build_newsapi_url,
    fetch_news,
)


# ---------------------------------------------------------------------------
# OpenFEC
# ---------------------------------------------------------------------------


class TestOpenFEC:
    def test_mock_mode(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
        result = fetch_openfec_finance("fed-123", "candidate", "test-key")
        assert result["entity_id"] == "fed-123"
        assert result["total_raised"] > 0

    def test_map_entity_type(self):
        assert _map_entity_type("IND") == "individual"
        assert _map_entity_type("PAC") == "PAC"
        assert _map_entity_type("ORG") == "corporation"
        assert _map_entity_type("UNKNOWN") is None

    def test_make_request_success(self, monkeypatch):
        body = json.dumps({"results": [{"id": "1"}]}).encode()
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda url, **kw: io.BytesIO(body),
        )
        result = _make_request("https://example.com")
        assert result["results"][0]["id"] == "1"

    def test_make_request_rate_limited(self, monkeypatch):
        def _raise_429(url, **kw):
            raise urllib.error.HTTPError(url, 429, "Rate Limited", {}, None)
        monkeypatch.setattr("urllib.request.urlopen", _raise_429)
        with pytest.raises(ValueError, match="RATE_LIMITED"):
            _make_request("https://example.com")

    def test_make_request_http_error(self, monkeypatch):
        def _raise_500(url, **kw):
            raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)
        monkeypatch.setattr("urllib.request.urlopen", _raise_500)
        with pytest.raises(ValueError, match="FINANCE_UNAVAILABLE"):
            _make_request("https://example.com")

    def test_make_request_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda url, **kw: io.BytesIO(b"not json"),
        )
        with pytest.raises(ValueError, match="invalid JSON"):
            _make_request("https://example.com")

    def test_real_mode_full_flow(self, monkeypatch):
        """Test the full non-mock flow with mocked HTTP."""
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_OPENFEC_API", "false")
        responses = [
            json.dumps({"results": [{"candidate_id": "H12345"}]}).encode(),
            json.dumps({"results": [{"receipts": 1000, "disbursements": 500, "cycle": 2026}]}).encode(),
            json.dumps({"results": [{"contributor_name": "Alice", "contribution_receipt_amount": 100, "entity_type": "IND"}]}).encode(),
        ]
        call_count = [0]

        def _mock_urlopen(url, **kw):
            idx = call_count[0]
            call_count[0] += 1
            return io.BytesIO(responses[idx])

        monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen)
        result = fetch_openfec_finance("fed-123", "candidate", "test-key")
        assert result["total_raised"] == 1000
        assert result["total_spent"] == 500
        assert len(result["top_donors"]) == 1


# ---------------------------------------------------------------------------
# FL Finance
# ---------------------------------------------------------------------------


class TestFLFinance:
    def test_mock_mode(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
        result = fetch_fl_finance("fl-123", "candidate")
        assert result["entity_id"] == "fl-123"
        assert result["total_raised"] > 0

    def test_parse_csv_contributions(self):
        csv_text = "candidate_id,contributor_name,amount,type\nfl-1,Alice,1000.00,contribution\nfl-1,Bob,500.00,contribution\nfl-2,Charlie,200.00,contribution"
        contributions, expenditures = _parse_csv(csv_text, "fl-1")
        assert len(contributions) == 2
        assert len(expenditures) == 0
        assert contributions[0]["contributor_name"] == "Alice"

    def test_parse_csv_expenditures(self):
        csv_text = "candidate_id,contributor_name,amount,type\nfl-1,Vendor A,5000.00,expenditure"
        contributions, expenditures = _parse_csv(csv_text, "fl-1")
        assert len(contributions) == 0
        assert len(expenditures) == 1

    def test_parse_csv_no_match(self):
        csv_text = "candidate_id,contributor_name,amount,type\nfl-2,Alice,1000.00,contribution"
        contributions, expenditures = _parse_csv(csv_text, "fl-1")
        assert contributions == []
        assert expenditures == []

    def test_safe_float_valid(self):
        assert _safe_float("123.45") == 123.45

    def test_safe_float_invalid(self):
        assert _safe_float("not a number") is None
        assert _safe_float(None) is None

    def test_real_mode_entity_not_found(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_FL_FINANCE_API", "false")
        csv_text = "candidate_id,contributor_name,amount,type\n"
        monkeypatch.setattr(
            "mcp_servers.ballot_data.sources.fl_finance._download_csv",
            lambda: csv_text,
        )
        with pytest.raises(ValueError, match="ENTITY_NOT_FOUND"):
            fetch_fl_finance("fl-nonexistent", "candidate")

    def test_real_mode_success(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_FL_FINANCE_API", "false")
        csv_text = "candidate_id,contributor_name,amount,type\nfl-1,Alice,1000.00,contribution\nfl-1,Bob,500.00,contribution"
        monkeypatch.setattr(
            "mcp_servers.ballot_data.sources.fl_finance._download_csv",
            lambda: csv_text,
        )
        result = fetch_fl_finance("fl-1", "candidate")
        assert result["total_raised"] == 1500.0
        assert len(result["top_donors"]) == 2
        assert result["sources"][0]["name"] == "Florida Division of Elections"


# ---------------------------------------------------------------------------
# NewsAPI
# ---------------------------------------------------------------------------


class TestNewsAPI:
    def test_mock_mode(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
        result = fetch_news("florida amendment", "test-key", None, None, 5)
        assert result["status"] == "ok"
        assert len(result["articles"]) == 2

    def test_build_url_basic(self):
        url = _build_newsapi_url("florida", "key123", None, None, 5)
        assert "q=florida" in url
        assert "apiKey=key123" in url
        assert "pageSize=5" in url

    def test_build_url_with_dates(self):
        url = _build_newsapi_url("test", "key", "2026-01-01", "2026-03-01", 10)
        assert "from=2026-01-01" in url
        assert "to=2026-03-01" in url

    def test_real_mode_success(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_NEWSAPI", "false")
        body = json.dumps({"status": "ok", "articles": []}).encode()

        class FakeResponse:
            def read(self):
                return body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda req, **kw: FakeResponse())
        result = fetch_news("test", "key", None, None, 5)
        assert result["status"] == "ok"

    def test_real_mode_rate_limited(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_NEWSAPI", "false")

        def _raise_429(req, **kw):
            raise urllib.error.HTTPError("url", 429, "Rate Limited", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", _raise_429)
        with pytest.raises(ValueError, match="rate limited"):
            fetch_news("test", "key", None, None, 5)


# ---------------------------------------------------------------------------
# Ballotpedia
# ---------------------------------------------------------------------------


class TestBallotpedia:
    def test_mock_mode_measure(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
        result = fetch_measure_from_ballotpedia("https://ballotpedia.org/test")
        assert "summary" in result
        assert result["sources"][0]["name"] == "Ballotpedia"

    def test_mock_mode_candidate(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
        result = fetch_candidate_from_ballotpedia("https://ballotpedia.org/test")
        assert "bio" in result

    def test_parse_measure_html(self):
        html = "<html><body><p>This is the measure text.</p><script>bad</script></body></html>"
        result = _parse_measure_html(html, "https://example.com")
        assert "measure text" in result["summary"]
        assert "bad" not in result["summary"]
        assert result["sources"][0]["url"] == "https://example.com"

    def test_parse_candidate_html(self):
        html = "<html><body><p>Jane Doe is a Florida politician.</p></body></html>"
        result = _parse_candidate_html(html, "https://example.com")
        assert "Jane Doe" in result["bio"]

    def test_text_extractor_skips_script(self):
        parser = _TextExtractor()
        parser.feed("<p>visible</p><script>hidden</script><p>also visible</p>")
        text = parser.get_text()
        assert "visible" in text
        assert "hidden" not in text
        assert "also visible" in text

    def test_text_extractor_skips_style(self):
        parser = _TextExtractor()
        parser.feed("<style>.x{color:red}</style><p>content</p>")
        assert "content" in parser.get_text()
        assert "color" not in parser.get_text()

    def test_real_mode_measure(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_BALLOTPEDIA_API", "false")

        class FakeResponse:
            def read(self):
                return b"<html><body><p>Amendment summary text here</p></body></html>"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda req, **kw: FakeResponse())
        result = fetch_measure_from_ballotpedia("https://ballotpedia.org/test")
        assert "Amendment summary" in result["summary"]

    def test_real_mode_http_error(self, monkeypatch):
        monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
        monkeypatch.setenv("MOCK_BALLOTPEDIA_API", "false")

        def _raise_404(req, **kw):
            raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", _raise_404)
        with pytest.raises(ValueError, match="BALLOTPEDIA_UNAVAILABLE"):
            fetch_measure_from_ballotpedia("https://ballotpedia.org/test")
