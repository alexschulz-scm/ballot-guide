"""Tests for llm_client.py — all use MOCK_LLM=true, no real API calls."""
import asyncio
import json
import logging

import pytest
from pydantic import BaseModel

from apps.api.orchestrator.llm_client import (
    LLMError,
    SchemaValidationError,
    _inline_refs,
    _prepare_gemini_schema,
    _strip_additional_properties,
    call_llm,
    load_prompt,
    parse_json_response,
)


class _SimpleSchema(BaseModel):
    name: str
    count: int


def _no_additional_properties(schema: dict) -> bool:
    """Return True only if additionalProperties is absent at every nesting level."""
    if "additionalProperties" in schema:
        return False
    for v in schema.values():
        if isinstance(v, dict) and not _no_additional_properties(v):
            return False
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and not _no_additional_properties(item):
                    return False
    return True


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


# ---------------------------------------------------------------------------
# Slice 5: response_schema parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_llm_with_schema_sets_mime_and_schema(real_api_mode, monkeypatch):
    """When response_schema is provided, GenerateContentConfig receives mime + a schema dict."""
    captured_config = {}

    class _CapturingModels:
        async def generate_content(self, *, model, contents, config):
            captured_config["config"] = config
            return _FakeResponse('{"name": "x", "count": 1}')

    class _CapturingAio:
        models = _CapturingModels()

    class _CapturingClient:
        def __init__(self, *args, **kwargs):
            self.aio = _CapturingAio()

    from google import genai
    monkeypatch.setattr(genai, "Client", _CapturingClient)

    await call_llm("sys", [{"role": "user", "content": "hi"}], response_schema=_SimpleSchema)

    cfg = captured_config["config"]
    assert cfg.response_mime_type == "application/json"
    # Schema is pre-processed: flat dict with no $ref/$defs and no additionalProperties
    assert isinstance(cfg.response_schema, dict)
    blob = json.dumps(cfg.response_schema)
    assert "$ref" not in blob
    assert "$defs" not in blob
    assert "additionalProperties" not in blob


@pytest.mark.asyncio
async def test_call_llm_schema_strips_additional_properties(real_api_mode, monkeypatch):
    """dict[str, str] fields generate additionalProperties — must be stripped for Gemini."""
    from pydantic import BaseModel

    class _DictField(BaseModel):
        positions: dict[str, str]
        name: str

    captured_schema: dict = {}

    class _CapturingModels:
        async def generate_content(self, *, model, contents, config):
            captured_schema.update(config.response_schema or {})
            return _FakeResponse('{"positions": {"housing": "pro-housing"}, "name": "x"}')

    class _CapturingAio:
        models = _CapturingModels()

    class _CapturingClient:
        def __init__(self, *args, **kwargs):
            self.aio = _CapturingAio()

    from google import genai
    monkeypatch.setattr(genai, "Client", _CapturingClient)

    await call_llm("sys", [{"role": "user", "content": "hi"}], response_schema=_DictField)

    assert _no_additional_properties(captured_schema), (
        "additionalProperties found in schema passed to Gemini"
    )


@pytest.mark.asyncio
async def test_call_llm_without_schema_omits_mime_type(real_api_mode, monkeypatch):
    """Without response_schema, GenerateContentConfig has no response_mime_type."""
    from google.genai import types

    captured_config = {}

    class _CapturingModels:
        async def generate_content(self, *, model, contents, config):
            captured_config["config"] = config
            return _FakeResponse('{"ok": true}')

    class _CapturingAio:
        models = _CapturingModels()

    class _CapturingClient:
        def __init__(self, *args, **kwargs):
            self.aio = _CapturingAio()

    from google import genai
    monkeypatch.setattr(genai, "Client", _CapturingClient)

    await call_llm("sys", [{"role": "user", "content": "hi"}])

    cfg = captured_config["config"]
    assert getattr(cfg, "response_mime_type", None) is None


def test_call_llm_mock_mode_unaffected_by_schema(mock_llm):
    """MOCK_LLM=true returns fixture regardless of response_schema."""
    result = asyncio.run(
        call_llm(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            response_schema=_SimpleSchema,
        )
    )
    assert result == '{"mock": true}'


# ---------------------------------------------------------------------------
# _strip_additional_properties unit tests
# ---------------------------------------------------------------------------


def test_strip_additional_properties_removes_top_level():
    schema = {"type": "object", "additionalProperties": {"type": "string"}}
    result = _strip_additional_properties(schema)
    assert "additionalProperties" not in result


def test_strip_additional_properties_removes_nested():
    schema = {
        "type": "object",
        "properties": {
            "positions": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            }
        },
    }
    _strip_additional_properties(schema)
    assert "additionalProperties" not in schema["properties"]["positions"]


def test_strip_additional_properties_handles_defs():
    schema = {
        "$defs": {
            "PositionMap": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            }
        },
        "properties": {"p": {"$ref": "#/$defs/PositionMap"}},
    }
    _strip_additional_properties(schema)
    assert "additionalProperties" not in schema["$defs"]["PositionMap"]


def test_strip_additional_properties_handles_list_items():
    schema = {
        "type": "array",
        "items": [{"type": "object", "additionalProperties": {"type": "string"}}],
    }
    _strip_additional_properties(schema)
    assert "additionalProperties" not in schema["items"][0]


def test_strip_additional_properties_noop_when_absent():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    original = dict(schema)
    _strip_additional_properties(schema)
    assert schema == original


# ---------------------------------------------------------------------------
# _inline_refs unit tests
# ---------------------------------------------------------------------------


def test_inline_refs_replaces_ref_with_definition():
    defs = {"Foo": {"type": "object", "properties": {"x": {"type": "string"}}}}
    node = {"$ref": "#/$defs/Foo"}
    result = _inline_refs(node, defs)
    assert result == {"type": "object", "properties": {"x": {"type": "string"}}}


def test_inline_refs_removes_defs_key():
    schema = {
        "$defs": {"Bar": {"type": "string"}},
        "properties": {"b": {"$ref": "#/$defs/Bar"}},
    }
    result = _inline_refs(schema, schema.get("$defs", {}))
    assert "$defs" not in result
    assert result["properties"]["b"] == {"type": "string"}


def test_inline_refs_handles_list_nodes():
    defs = {"Tag": {"type": "string"}}
    node = [{"$ref": "#/$defs/Tag"}, {"type": "integer"}]
    result = _inline_refs(node, defs)
    assert result == [{"type": "string"}, {"type": "integer"}]


def test_inline_refs_noop_on_scalar():
    assert _inline_refs("hello", {}) == "hello"
    assert _inline_refs(42, {}) == 42


# ---------------------------------------------------------------------------
# _prepare_gemini_schema integration tests
# ---------------------------------------------------------------------------


def test_prepare_gemini_schema_no_refs_remaining():
    """The output schema must have no $ref or $defs anywhere."""
    from apps.api.orchestrator.schemas import CandidateAnalysis

    result = _prepare_gemini_schema(CandidateAnalysis)
    blob = json.dumps(result)
    assert "$ref" not in blob
    assert "$defs" not in blob


def test_prepare_gemini_schema_no_additional_properties():
    """CandidateAnalysis.positions (dict[str, str]) must not produce additionalProperties."""
    from apps.api.orchestrator.schemas import CandidateAnalysis

    result = _prepare_gemini_schema(CandidateAnalysis)
    assert _no_additional_properties(result)


def test_prepare_gemini_schema_preserves_required_fields():
    """Required fields on the top-level schema survive the transformation."""
    from apps.api.orchestrator.schemas import MeasureAnalysis

    result = _prepare_gemini_schema(MeasureAnalysis)
    assert "properties" in result
    assert "measure_id" in result.get("properties", {})
