"""
Tests for claude_client security hardening: path traversal guard, mock loading.
"""

import pytest

from apps.api.orchestrator.claude_client import (
    SchemaValidationError,
    _strip_code_fences,
    load_prompt,
    parse_json_response,
)
from apps.api.orchestrator.schemas import IntakeResult


# ---------------------------------------------------------------------------
# Path traversal guard (#16)
# ---------------------------------------------------------------------------


class TestLoadPromptSecurity:
    def test_valid_prompt_loads(self):
        text = load_prompt("system")
        assert len(text) > 0

    def test_path_traversal_dotdot(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("../../../etc/passwd")

    def test_path_traversal_forward_slash(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("prompts/system")

    def test_path_traversal_backslash(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load_prompt("prompts\\system")

    def test_nonexistent_prompt(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt_name")


# ---------------------------------------------------------------------------
# Code fence stripping
# ---------------------------------------------------------------------------


class TestStripCodeFences:
    def test_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert _strip_code_fences(text) == '{"key": "value"}'

    def test_no_fence(self):
        text = '{"key": "value"}'
        assert _strip_code_fences(text) == '{"key": "value"}'

    def test_plain_fence(self):
        text = '```\n{"key": "value"}\n```'
        assert _strip_code_fences(text) == '{"key": "value"}'


# ---------------------------------------------------------------------------
# parse_json_response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_json_valid():
    text = '{"zip_code":"33101","address_full":null,"priorities":["housing"],"priorities_raw":"housing","display_name":null,"needs_clarification":false,"clarification_question":null}'
    result = await parse_json_response(text, IntakeResult)
    assert result.zip_code == "33101"


@pytest.mark.asyncio
async def test_parse_json_invalid():
    with pytest.raises(SchemaValidationError, match="Invalid JSON"):
        await parse_json_response("not json at all", IntakeResult)


@pytest.mark.asyncio
async def test_parse_json_schema_mismatch():
    with pytest.raises(SchemaValidationError, match="Schema validation failed"):
        await parse_json_response('{"wrong_field": true}', IntakeResult)


@pytest.mark.asyncio
async def test_parse_json_with_fence():
    text = '```json\n{"zip_code":"33101","address_full":null,"priorities":["housing"],"priorities_raw":"housing","display_name":null,"needs_clarification":false,"clarification_question":null}\n```'
    result = await parse_json_response(text, IntakeResult)
    assert result.zip_code == "33101"
