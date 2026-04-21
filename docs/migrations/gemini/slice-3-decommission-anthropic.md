# Slice 3 — Decommission Anthropic

## Goal

Remove every trace of the Anthropic dependency and `ANTHROPIC_*` / `MOCK_CLAUDE` environment plumbing from app code, config, and tests. Infra and docs are cleaned up in later slices.

## Context

After Slice 2, the Anthropic SDK is installed but unused. This slice deletes it. AC-17 (startup fails without an LLM API key) now applies to `GEMINI_API_KEY`.

## Changes

### `requirements.txt`
- Remove the `anthropic~=0.84.0` line.

### `apps/api/config.py`
- Remove the `ANTHROPIC_API_KEY: str` setting.
- Remove the `MOCK_CLAUDE: bool = False` setting.
- `GEMINI_API_KEY` is now the sole required LLM key.

### `.env.example`
- Remove the `ANTHROPIC_API_KEY` line (and its "removed in Slice 3" comment from Slice 1).
- Remove any `MOCK_CLAUDE` reference.

### `tests/api/conftest.py`
- Remove `os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")`.
- Remove `os.environ.setdefault("MOCK_CLAUDE", "true")`.
- Keep the `GEMINI_API_KEY` and `MOCK_LLM` defaults from Slice 1.

### `tests/api/test_security.py`
- Remove the `ANTHROPIC_API_KEY` and `MOCK_CLAUDE` env-var setup from the top of the file.

### `tests/api/test_startup.py` — AC-17 test
- Rewrite the test that asserts startup fails without `ANTHROPIC_API_KEY` to instead assert it fails without `GEMINI_API_KEY`.
- Update the assertion in the "keys are loaded" test: `settings.ANTHROPIC_API_KEY` → `settings.GEMINI_API_KEY`.

### Grep sweep (safety net)

Run each of these and clean any remaining hits in `apps/` and `tests/`:
- `rg -i 'anthropic' apps tests`
- `rg 'ANTHROPIC_API_KEY' apps tests`
- `rg 'MOCK_CLAUDE' apps tests`
- `rg 'call_claude|ClaudeError' apps tests`
- `rg 'claude_client' apps tests`

Do NOT touch:
- `docs/` — cleaned in Slice 7
- `CLAUDE.md` — cleaned in Slice 7
- `.github/workflows/` — cleaned in Slice 4
- `infra/` — cleaned in Slice 4
- `STATUS.md` / `ROADMAP.md` — historical references kept, updated in Slice 7

## Acceptance criteria

- [ ] `rg -i 'anthropic' apps tests` returns zero hits
- [ ] `rg 'ANTHROPIC_API_KEY|MOCK_CLAUDE' apps tests` returns zero hits
- [ ] `pip install -r requirements.txt` does not install `anthropic`
- [ ] `pip show anthropic` fails in a fresh venv after `pip install -r requirements.txt`
- [ ] Full test suite passes
- [ ] AC-17 test passes for `GEMINI_API_KEY` (not `ANTHROPIC_API_KEY`)
- [ ] App boots with only `GEMINI_API_KEY` set (no Anthropic key present)

## Out of scope (deferred)

- Infra Bicep and GitHub Actions cleanup — Slice 4
- Doc and spec text updates — Slice 7
- Rotating the production GitHub / Azure secret — Slice 4

## Manual steps

None. Pure code change.

## Rollback

Revert the single commit. Slice 2's client still works because it only referenced Anthropic symbols during the rewrite phase — none are live at this point.
