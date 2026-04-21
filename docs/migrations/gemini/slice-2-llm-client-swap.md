# Slice 2 — LLM client swap

## Goal

The orchestrator runs on Gemini end-to-end. All 5 stages route through a renamed, rewritten `llm_client.py`. Anthropic SDK is still installed (removed in Slice 3) but no longer imported.

## Context

This is the biggest, riskiest slice. Keep the public interface of the client module stable so the diff in stages is purely import renames and symbol renames — no logic changes in stage code.

## Changes

### Rename module
- `apps/api/orchestrator/claude_client.py` → `apps/api/orchestrator/llm_client.py`

### Rename public symbols (in `llm_client.py`)
- `call_claude` → `call_llm`
- `ClaudeError` → `LLMError`
- `parse_json_response` — unchanged
- `load_prompt` — unchanged
- `SchemaValidationError` — unchanged
- Internal model constant `_MODEL` — delete; model now comes from `settings.GEMINI_MODEL` on each call.

### Rewrite `_call_real_api` in `llm_client.py`

Replace the `anthropic.AsyncAnthropic` path with `google.genai`:

- Import: `from google import genai`, `from google.genai import types, errors`
- Client init: `client = genai.Client(api_key=settings.GEMINI_API_KEY)`
- Model: `settings.GEMINI_MODEL` (read per call, not cached at module level, so tests can override)
- Temperature: `0.1` — still hardcoded. Per `CLAUDE.md` line 181.
- System prompt placement: pass as `config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.1, max_output_tokens=max_tokens)` — NOT inside `contents`.
- Message role translation at the boundary: incoming list uses `"user"` / `"assistant"`. Convert to Gemini's `"user"` / `"model"` when building the `contents` list. Do this inside `_call_real_api`; stage code keeps using `"assistant"`.
- Call: `response = await client.aio.models.generate_content(model=settings.GEMINI_MODEL, contents=<converted>, config=<config>)`
- Response text: `response.text`
- Usage logging: read `response.usage_metadata.prompt_token_count` and `response.usage_metadata.candidates_token_count`. Keep the existing log message format (`"token_usage input=%d output=%d"`) so dashboards/greps don't break.
- Error handling: catch `errors.APIError` (and `errors.ClientError` if distinct), wrap in `LLMError` with the same message shape.

### Mock mode

- Change the env-var check: `MOCK_CLAUDE` → `MOCK_LLM`.
- Move the mock fixture: `tests/fixtures/claude/mock_response.json` → `tests/fixtures/llm/mock_response.json`. Content unchanged (`{"mock": true}`).
- Update the path constant in `_load_mock_response()`.

### Update stage imports

In each of these files, change `from apps.api.orchestrator.claude_client import ...` to `from apps.api.orchestrator.llm_client import ...` and rename `call_claude` → `call_llm`, `ClaudeError` → `LLMError`:

- `apps/api/orchestrator/stages/intake.py`
- `apps/api/orchestrator/stages/measure_analyst.py`
- `apps/api/orchestrator/stages/candidate_analyst.py`
- `apps/api/orchestrator/stages/relevance_ranker.py`
- `apps/api/orchestrator/stages/follow_up.py`

No other logic in these files should change.

### Rename tests
- `tests/orchestrator/test_claude_client.py` → `tests/orchestrator/test_llm_client.py`
- `tests/orchestrator/test_claude_client_security.py` → `tests/orchestrator/test_llm_client_security.py`
- Update imports and symbol references inside both files.
- The `MOCK_CLAUDE=true` line at the top → `MOCK_LLM=true`.

## Acceptance criteria

- [ ] `rg 'claude_client|call_claude|ClaudeError|MOCK_CLAUDE' apps tests` returns zero hits in code (CLAUDE.md and docs cleaned up later)
- [ ] `rg 'import anthropic|from anthropic' apps` returns zero hits
- [ ] Full test suite passes with mocks on
- [ ] Manual smoke: with a real `GEMINI_API_KEY`, run `runner.py` against one seed ballot and verify it produces a parseable report
- [ ] Token-usage log lines still parse with existing regexes (`input=%d output=%d` format preserved)
- [ ] Temperature is still `0.1` (not parameterized)
- [ ] `settings.GEMINI_MODEL` is read on every call, not cached at import time

## Out of scope (deferred)

- Removing `anthropic` dep and `ANTHROPIC_API_KEY` from config — Slice 3
- Native JSON schema enforcement via `response_schema` — Slice 5
- Updating `CLAUDE.md`'s "No Claude calls outside `claude_client.py`" rule wording — Slice 7 (temporarily violated in wording only)

## Manual steps

- Obtain a personal `GEMINI_API_KEY` from Google AI Studio for local smoke-testing. Put it in your local `.env`, not committed.

## Rollback

Revert the single commit. Slice 1 already added the Gemini dep so the revert does not re-introduce install issues. All stage code returns to calling `claude_client` cleanly.
