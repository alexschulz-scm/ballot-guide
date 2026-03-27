"""
Thin wrapper around the Anthropic SDK for the orchestrator.

All Claude API calls go through this module — nowhere else.
Temperature is fixed at 0.1 (CLAUDE.md rule — not configurable per call).
Checks MOCK_CLAUDE=true before making any real API calls.

Exports:
    call_claude       — async, calls Claude Sonnet or returns mock
    parse_json_response — async, strips fences + validates against Pydantic schema
    load_prompt       — sync, loads .txt file from prompts/ directory
    ClaudeError       — raised on API failure
    SchemaValidationError — raised on JSON parse or schema validation failure
"""

import json
import logging
import os
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-sonnet-4-6"
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MOCK_FIXTURES_DIR = (
    Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "claude"
)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ClaudeError(Exception):
    """Raised when the Claude API call fails. Never wraps raw Anthropic exceptions."""


class SchemaValidationError(Exception):
    """Raised when Claude's response cannot be parsed into the expected schema."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_claude(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4000,
    _mock_file: str | None = None,
) -> str:
    """
    Call Claude Sonnet and return the response text.
    Temperature is always 0.1 (fixed per CLAUDE.md).
    Raises ClaudeError on API failure.
    """
    if _is_mock_mode():
        text = _load_mock_response(_mock_file)
        logger.info("token_usage mock input=0 output=%d", len(text))
        return text

    return await _call_real_api(system_prompt, messages, max_tokens)


async def _call_real_api(system_prompt, messages, max_tokens):
    """Make a real Anthropic API call. Raises ClaudeError on failure."""
    try:
        import anthropic  # deferred — only needed for real API calls
    except ImportError as exc:
        raise ClaudeError("anthropic package not installed") from exc

    try:
        from apps.api.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=_MODEL, max_tokens=max_tokens, temperature=0.1,
            system=system_prompt, messages=messages,
        )
        usage = response.usage
        logger.info(
            "token_usage input=%d output=%d",
            usage.input_tokens, usage.output_tokens,
        )
        return response.content[0].text
    except anthropic.APIError as exc:
        raise ClaudeError(f"Anthropic API error: {exc}") from exc
    except Exception as exc:
        raise ClaudeError(f"Unexpected error calling Claude: {exc}") from exc


async def parse_json_response(
    response_text: str,
    schema: type[BaseModel],
) -> BaseModel:
    """
    Parse Claude's response text as JSON and validate against a Pydantic schema.

    Strips markdown code fences (```json ... ```) before parsing.
    Raises SchemaValidationError — never raw JSONDecodeError or ValidationError.
    """
    text = _strip_code_fences(response_text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(
            f"Invalid JSON from Claude: {exc}\nResponse: {text[:300]}"
        ) from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(
            f"Schema validation failed for {schema.__name__}: {exc}"
        ) from exc


def load_prompt(prompt_name: str) -> str:
    """
    Load prompt text from apps/api/orchestrator/prompts/{prompt_name}.txt.

    Raises FileNotFoundError if the prompt file does not exist.
    Raises ValueError if the prompt name contains path traversal characters.
    """
    if ".." in prompt_name or "/" in prompt_name or "\\" in prompt_name:
        raise ValueError(f"Invalid prompt name: {prompt_name}")
    path = (_PROMPTS_DIR / f"{prompt_name}.txt").resolve()
    if not path.is_relative_to(_PROMPTS_DIR.resolve()):
        raise ValueError(f"Prompt path escapes prompts directory: {prompt_name}")
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_mock_mode() -> bool:
    return os.environ.get("MOCK_CLAUDE", "false").lower() == "true"


def _load_mock_response(mock_file: str | None) -> str:
    if mock_file:
        return (_MOCK_FIXTURES_DIR / mock_file).read_text(encoding="utf-8")
    return '{"mock": true}'


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from the start and end of a string."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()
