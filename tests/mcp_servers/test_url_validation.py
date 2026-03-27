"""
Tests for URL validation on SourceCitation model (#12).
"""

import pytest
from pydantic import ValidationError

from mcp_servers.shared.models import SourceCitation


class TestSourceCitationUrlValidation:
    def test_valid_https_url(self):
        s = SourceCitation(
            name="Test", url="https://example.com", fetched_at="2026-01-01T00:00:00Z", bias_rating=None
        )
        assert s.url == "https://example.com"

    def test_valid_http_url(self):
        s = SourceCitation(
            name="Test", url="http://example.com", fetched_at="2026-01-01T00:00:00Z", bias_rating=None
        )
        assert s.url == "http://example.com"

    def test_rejects_javascript_url(self):
        with pytest.raises(ValidationError, match="Invalid URL scheme"):
            SourceCitation(
                name="Test", url="javascript:alert('xss')", fetched_at="2026-01-01T00:00:00Z", bias_rating=None
            )

    def test_rejects_data_url(self):
        with pytest.raises(ValidationError, match="Invalid URL scheme"):
            SourceCitation(
                name="Test", url="data:text/html,<script>alert(1)</script>", fetched_at="2026-01-01T00:00:00Z", bias_rating=None
            )

    def test_rejects_ftp_url(self):
        with pytest.raises(ValidationError, match="Invalid URL scheme"):
            SourceCitation(
                name="Test", url="ftp://example.com/file", fetched_at="2026-01-01T00:00:00Z", bias_rating=None
            )

    def test_allows_relative_url(self):
        """Relative URLs (no scheme) should be allowed."""
        s = SourceCitation(
            name="Test", url="/path/to/resource", fetched_at="2026-01-01T00:00:00Z", bias_rating=None
        )
        assert s.url == "/path/to/resource"
