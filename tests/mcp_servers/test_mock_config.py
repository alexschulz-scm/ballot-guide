"""Tests for mcp_servers.shared.mock_config — per-source mock resolution."""

import os

import pytest

from mcp_servers.shared.mock_config import is_mock_mode


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure no mock flags leak between tests."""
    monkeypatch.delenv("MOCK_EXTERNAL_APIS", raising=False)
    monkeypatch.delenv("MOCK_CIVIC_API", raising=False)
    monkeypatch.delenv("MOCK_NEWSAPI", raising=False)


def test_master_override_true_mocks_all(monkeypatch):
    """When MOCK_EXTERNAL_APIS=true, every source is mocked."""
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
    assert is_mock_mode("MOCK_CIVIC_API") is True
    assert is_mock_mode("MOCK_NEWSAPI") is True
    assert is_mock_mode("MOCK_OPENFEC_API") is True


def test_master_override_false_allows_per_source(monkeypatch):
    """When master is false, per-source flags are respected."""
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "false")
    monkeypatch.setenv("MOCK_CIVIC_API", "true")
    assert is_mock_mode("MOCK_CIVIC_API") is True
    assert is_mock_mode("MOCK_NEWSAPI") is False


def test_no_flags_set_returns_false():
    """When nothing is set, no sources are mocked."""
    assert is_mock_mode("MOCK_CIVIC_API") is False
    assert is_mock_mode("MOCK_NEWSAPI") is False


def test_per_source_true_without_master(monkeypatch):
    """Per-source flag works when master is unset."""
    monkeypatch.setenv("MOCK_NEWSAPI", "true")
    assert is_mock_mode("MOCK_NEWSAPI") is True
    assert is_mock_mode("MOCK_CIVIC_API") is False


def test_master_true_overrides_per_source_false(monkeypatch):
    """Master override wins even if per-source is explicitly false."""
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")
    monkeypatch.setenv("MOCK_CIVIC_API", "false")
    assert is_mock_mode("MOCK_CIVIC_API") is True


def test_case_insensitive_values(monkeypatch):
    """Both True/TRUE/true work."""
    monkeypatch.setenv("MOCK_CIVIC_API", "True")
    assert is_mock_mode("MOCK_CIVIC_API") is True
    monkeypatch.setenv("MOCK_CIVIC_API", "TRUE")
    assert is_mock_mode("MOCK_CIVIC_API") is True


def test_sources_are_independent(monkeypatch):
    """Setting one source flag doesn't affect others."""
    monkeypatch.setenv("MOCK_CIVIC_API", "true")
    monkeypatch.setenv("MOCK_NEWSAPI", "false")
    assert is_mock_mode("MOCK_CIVIC_API") is True
    assert is_mock_mode("MOCK_NEWSAPI") is False
    assert is_mock_mode("MOCK_OPENFEC_API") is False
