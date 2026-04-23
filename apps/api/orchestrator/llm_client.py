"""
Thin wrapper around the Google Gemini SDK for the orchestrator.

All LLM API calls go through this module — nowhere else.
Temperature is fixed at 0.1 (CLAUDE.md rule — not configurable per call).
Checks MOCK_LLM=true before making any real API calls.

Exports:
    call_llm              — async, calls Gemini or returns mock
    parse_json_response   — async, strips fences + validates against Pydantic schema
    load_prompt           — sync, loads .txt file from prompts/ directory
    LLMError              — raised on API failure
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

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MOCK_FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "llm"

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised when the LLM API call fails. Never wraps raw SDK exceptions."""


class SchemaValidationError(Exception):
    """Raised when the LLM's response cannot be parsed into the expected schema."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_llm(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4000,
    response_schema: type[BaseModel] | None = None,
    _mock_file: str | None = None,
) -> str:
    """
    Call Gemini and return the response text.
    Temperature is always 0.1 (fixed per CLAUDE.md).
    When response_schema is provided, Gemini enforces JSON mode at the API level.
    Raises LLMError on API failure.
    """
    if _is_mock_mode():
        text = _load_mock_response(_mock_file)
        logger.info("token_usage mock input=0 output=%d", len(text))
        return text

    return await _call_real_api(system_prompt, messages, max_tokens, response_schema)


async def _call_real_api(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int,
    response_schema: type[BaseModel] | None = None,
) -> str:
    """Make a real Gemini API call. Raises LLMError on failure."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as exc:
        raise LLMError("google-genai package not installed") from exc

    try:
        from apps.api.config import settings

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else m["role"],
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]
        config_kwargs: dict = {
            "system_instruction": system_prompt,
            "temperature": 0.1,
            "max_output_tokens": max_tokens,
            # Disable thinking tokens so the full max_output_tokens budget goes
            # to the actual response (thinking consumes the budget silently on
            # gemini-2.5-flash, leaving only ~20 tokens for JSON output).
            "thinking_config": types.ThinkingConfig(thinking_budget=0),
        }
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            # Gemini's dict-mode schema parser does not resolve $ref/$defs and
            # rejects additionalProperties. Inline all refs and strip that key
            # before passing.
            config_kwargs["response_schema"] = _prepare_gemini_schema(response_schema)
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        logger.info(
            "token_usage input=%d output=%d",
            response.usage_metadata.prompt_token_count,
            response.usage_metadata.candidates_token_count,
        )
        return response.text
    except (errors.APIError, errors.ClientError) as exc:
        raise LLMError(f"Gemini API error: {exc}") from exc
    except Exception as exc:
        raise LLMError(f"Unexpected error calling Gemini: {exc}") from exc


async def parse_json_response(
    response_text: str,
    schema: type[BaseModel],
) -> BaseModel:
    """
    Parse the LLM's response as JSON and validate against a Pydantic schema.

    Strips markdown code fences (```json ... ```) before parsing.
    Raises SchemaValidationError — never raw JSONDecodeError or ValidationError.
    """
    text = _strip_code_fences(response_text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(
            f"Invalid JSON from LLM: {exc}\nResponse: {text[:300]}"
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
    return os.environ.get("MOCK_LLM", "false").lower() == "true"


def _load_mock_response(mock_file: str | None) -> str:
    path = _MOCK_FIXTURES_DIR / (mock_file or "mock_response.json")
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return '{"mock": true}'


def _prepare_gemini_schema(schema_class: type[BaseModel]) -> dict:
    """Convert a Pydantic model to a Gemini-compatible flat JSON schema dict.

    Two transformations required:
    1. Inline all $ref/$defs — Gemini's dict-mode schema parser does not
       resolve JSON Schema references; every type must be described inline.
    2. Strip additionalProperties — produced by dict[K, V] fields; Gemini
       rejects it.
    """
    raw = schema_class.model_json_schema()
    defs = raw.get("$defs", {})
    inlined = _inline_refs(raw, defs)
    _strip_additional_properties(inlined)
    return inlined


def _inline_refs(node: object, defs: dict) -> object:
    """Recursively replace every {"$ref": "#/$defs/Foo"} with the inlined def."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            return _inline_refs(dict(defs.get(ref_name, {})), defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    return node


def _strip_additional_properties(schema: dict) -> dict:
    """Remove additionalProperties recursively from a JSON schema dict."""
    schema.pop("additionalProperties", None)
    for value in schema.values():
        if isinstance(value, dict):
            _strip_additional_properties(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _strip_additional_properties(item)
    return schema


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from the start and end of a string."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()
