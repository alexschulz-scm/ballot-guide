"""Tests for claude_client.py — all use MOCK_CLAUDE=true, no real API calls."""
import asyncio
import logging

import pytest
from pydantic import BaseModel

from apps.api.orchestrator.claude_client import (
    ClaudeError,
    SchemaValidationError,
    call_claude,
    load_prompt,
    parse_json_response,
)


class _SimpleSchema(BaseModel):
    name: str
    count: int


@pytest.fixture(autouse=False)
def mock_claude(monkeypatch):
    monkeypatch.setenv("MOCK_CLAUDE", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# call_claude tests
# ---------------------------------------------------------------------------


def test_call_claude_uses_mock_when_env_set(mock_claude):
    """MOCK_CLAUDE=true returns without calling Anthropic API."""
    result = asyncio.run(
        call_claude(
            system_prompt="You are a test assistant.",
            messages=[{"role": "user", "content": "Hello"}],
        )
    )
    # Default mock returns '{"mock": true}'
    assert result == '{"mock": true}'


def test_call_claude_logs_token_usage(mock_claude, caplog):
    """MOCK_CLAUDE=true path still logs token_usage line."""
    with caplog.at_level(logging.INFO, logger="apps.api.orchestrator.claude_client"):
        asyncio.run(
            call_claude(
                system_prompt="You are a test assistant.",
                messages=[{"role": "user", "content": "Hello"}],
            )
        )
    assert any("token_usage" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# parse_json_response tests
# ---------------------------------------------------------------------------


def test_parse_json_response_valid_json_returns_model(mock_claude):
    """Valid JSON string produces correct Pydantic model."""
    result = asyncio.run(
        parse_json_response('{"name": "Alice", "count": 42}', _SimpleSchema)
    )
    assert isinstance(result, _SimpleSchema)
    assert result.name == "Alice"
    assert result.count == 42


def test_parse_json_response_strips_markdown_fences(mock_claude):
    """Input wrapped in ```json...``` fences parses correctly."""
    fenced = "```json\n{\"name\": \"Bob\", \"count\": 7}\n```"
    result = asyncio.run(parse_json_response(fenced, _SimpleSchema))
    assert isinstance(result, _SimpleSchema)
    assert result.name == "Bob"
    assert result.count == 7


def test_parse_json_response_invalid_json_raises_schema_validation_error(mock_claude):
    """Malformed JSON raises SchemaValidationError, not JSONDecodeError."""
    with pytest.raises(SchemaValidationError, match="Invalid JSON"):
        asyncio.run(parse_json_response("{not valid json}", _SimpleSchema))


def test_parse_json_response_missing_required_field_raises_error(mock_claude):
    """Valid JSON missing a required field raises SchemaValidationError."""
    with pytest.raises(SchemaValidationError, match="Schema validation failed"):
        asyncio.run(parse_json_response('{"name": "Carol"}', _SimpleSchema))


# ---------------------------------------------------------------------------
# load_prompt tests
# ---------------------------------------------------------------------------


def test_load_prompt_returns_file_contents():
    """load_prompt('system') returns a non-empty string from the prompts dir."""
    content = load_prompt("system")
    assert isinstance(content, str)
    assert len(content) > 0


def test_load_prompt_raises_on_missing_file():
    """load_prompt with a nonexistent prompt name raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt_that_does_not_exist")
