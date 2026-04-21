# Slice 1 — Config scaffolding

## Goal

Add Gemini SDK and configuration alongside the existing Anthropic setup. Nothing calls Gemini yet. Tree remains green. Non-breaking.

## Context

This slice lays the groundwork so Slice 2 can be a focused, purely-internal swap of the LLM client. After this slice, `settings.GEMINI_*` values are loaded but unused.

## Changes

### `requirements.txt`
- Add `google-genai~=<latest stable>` as a new line. Keep `anthropic~=0.84.0` in place — it is removed in Slice 3.

### `apps/api/config.py`
Add three new settings to the existing Pydantic `Settings` class:
- `GEMINI_API_KEY: str` — required, no default. Raises on startup if missing once wired up (Slice 3 makes this the sole required LLM key).
- `GEMINI_MODEL: str = "gemini-2.5-flash"` — default, overridable.
- `MOCK_LLM: bool = False` — mirrors the existing `MOCK_CLAUDE` flag; becomes the sole mock flag in Slice 3.

Keep `ANTHROPIC_API_KEY` and `MOCK_CLAUDE` as they are. Do not remove them.

### `.env.example`
Add the three new vars with placeholder values. Add a comment above each old Anthropic var noting it is removed in the migration:
```
# Removed in Gemini migration (Slice 3)
ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

### `tests/api/conftest.py`
Alongside the existing `os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")` and `MOCK_CLAUDE=true`, add:
- `os.environ.setdefault("GEMINI_API_KEY", "test-key")`
- `os.environ.setdefault("MOCK_LLM", "true")`

## Acceptance criteria

- [ ] `pip install -r requirements.txt` installs `google-genai` without conflicts
- [ ] `from google import genai` succeeds in a Python REPL
- [ ] App boots with both key sets present in the environment
- [ ] `settings.GEMINI_MODEL` returns `"gemini-2.5-flash"` when the env var is unset
- [ ] `settings.GEMINI_MODEL` returns the env value when overridden
- [ ] Full test suite passes with no changes to stage or orchestrator code
- [ ] No file under `apps/api/orchestrator/` is modified in this slice

## Out of scope (deferred)

- Any code path that actually calls Gemini — Slice 2
- Removing `ANTHROPIC_API_KEY` / `MOCK_CLAUDE` — Slice 3
- Updating `CLAUDE.md` env var table — Slice 7

## Manual steps

None. Pure code change.

## Rollback

Revert the single commit. No state outside the repo is touched.
