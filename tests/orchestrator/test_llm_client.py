"""Tests for llm_client.py — all use MOCK_LLM=true, no real API calls."""
import asyncio
import logging

import pytest
from pydantic import BaseModel

from apps.api.orchestrator.llm_client import (
    LLMError,
    SchemaValidationError,
    call_llm,
    load_prompt,
    parse_json_response,
)


class _SimpleSchema(BaseModel):
    name: str
    count: int


@pytest.fixture(autouse=False)
def mock_llm(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# call_llm tests
# ---------------------------------------------------------------------------


def test_call_llm_uses_mock_when_env_set(mock_llm):
    """MOCK_LLM=true returns without calling Gemini API."""
    result = asyncio.run(
        call_llm(
            system_prompt="You are a test assistant.",
            messages=[{"role": "user", "content": "Hello"}],
        )
    )
    assert result == '{"mock": true}'


def test_call_llm_logs_token_usage(mock_llm, caplog):
    """MOCK_LLM=true path still logs token_usage line."""
    with caplog.at_level(logging.INFO, logger="apps.api.orchestrator.llm_client"):
        asyncio.run(
            call_llm(
                system_prompt="You are a test assistant.",
                messages=[{"role": "user", "content": "Hello"}],
            )
        )
    assert any("token_usage" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# parse_json_response tests
# ---------------------------------------------------------------------------


def test_parse_json_response_valid_json_returns_model(mock_llm):
    """Valid JSON string produces correct Pydantic model."""
    result = asyncio.run(
        parse_json_response('{"name": "Alice", "count": 42}', _SimpleSchema)
    )
    assert isinstance(result, _SimpleSchema)
    assert result.name == "Alice"
    assert result.count == 42


def test_parse_json_response_strips_markdown_fences(mock_llm):
    """Input wrapped in ```json...``` fences parses correctly."""
    fenced = "```json\n{\"name\": \"Bob\", \"count\": 7}\n```"
    result = asyncio.run(parse_json_response(fenced, _SimpleSchema))
    assert isinstance(result, _SimpleSchema)
    assert result.name == "Bob"
    assert result.count == 7


def test_parse_json_response_invalid_json_raises_schema_validation_error(mock_llm):
    """Malformed JSON raises SchemaValidationError, not JSONDecodeError."""
    with pytest.raises(SchemaValidationError, match="Invalid JSON"):
        asyncio.run(parse_json_response("{not valid json}", _SimpleSchema))


def test_parse_json_response_missing_required_field_raises_error(mock_llm):
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


# ---------------------------------------------------------------------------
# Mock fallback: fixture file missing
# ---------------------------------------------------------------------------


def test_call_llm_mock_fallback_when_fixture_missing(mock_llm):
    """When _mock_file points to a non-existent file, falls back to hardcoded JSON."""
    result = asyncio.run(
        call_llm(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            _mock_file="does_not_exist.json",
        )
    )
    assert result == '{"mock": true}'


# ---------------------------------------------------------------------------
# Real API path — stub out google.genai SDK
# ---------------------------------------------------------------------------


class _FakeUsage:
    def __init__(self, pi: int, po: int):
        self.prompt_token_count = pi
        self.candidates_token_count = po


class _FakeResponse:
    def __init__(self, text: str, pi: int = 5, po: int = 7):
        self.text = text
        self.usage_metadata = _FakeUsage(pi, po)


def _install_fake_genai_client(monkeypatch, *, response_text=None, raise_exc=None):
    """Patch google.genai.Client to return a fake async client."""
    from google import genai

    class _FakeModels:
        async def generate_content(self, **kwargs):
            if raise_exc is not None:
                raise raise_exc
            return _FakeResponse(response_text or '{"ok": true}')

    class _FakeAio:
        models = _FakeModels()

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.aio = _FakeAio()

    monkeypatch.setattr(genai, "Client", _FakeClient)


@pytest.fixture
def real_api_mode(monkeypatch):
    """Force non-mock mode with a dummy API key."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")


@pytest.mark.asyncio
async def test_call_llm_real_api_happy_path(real_api_mode, monkeypatch, caplog):
    """Real API path maps roles, returns text, logs token usage."""
    _install_fake_genai_client(monkeypatch, response_text='{"result": "ok"}')
    with caplog.at_level(logging.INFO, logger="apps.api.orchestrator.llm_client"):
        result = await call_llm(
            system_prompt="sys",
            messages=[
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "second"},
            ],
        )
    assert result == '{"result": "ok"}'
    assert any(
        "token_usage input=5 output=7" in r.message for r in caplog.records
    )


@pytest.mark.asyncio
async def test_call_llm_real_api_wraps_api_error(real_api_mode, monkeypatch):
    """APIError from Gemini SDK is wrapped in LLMError."""
    from google.genai import errors

    api_err = errors.APIError.__new__(errors.APIError)
    api_err.args = ("rate limited",)
    _install_fake_genai_client(monkeypatch, raise_exc=api_err)
    with pytest.raises(LLMError, match="Gemini API error"):
        await call_llm("sys", [{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_call_llm_real_api_wraps_unexpected_error(real_api_mode, monkeypatch):
    """Non-API exceptions are wrapped in LLMError via the generic branch."""
    _install_fake_genai_client(monkeypatch, raise_exc=RuntimeError("boom"))
    with pytest.raises(LLMError, match="Unexpected error"):
        await call_llm("sys", [{"role": "user", "content": "hi"}])
