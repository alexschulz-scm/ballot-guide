# Slice 7 — Docs & rules

## Goal

Repo documentation reflects reality. A grep for "Claude" or "anthropic" returns only intentional references (changelog/historical notes, or the `CLAUDE.md` filename itself, which stays).

## Context

`CLAUDE.md` keeps its filename — it is context for Claude Code (the editing tool), not for the app's LLM. Its contents need updating.

This is the final slice. After it lands, the migration is complete.

## Changes

### `CLAUDE.md`

- Tech Stack table: `Agent | Claude Sonnet via Anthropic SDK, tool-use loop` → `Agent | Gemini via google-genai SDK, directed LLM pipeline`
- Environment Variables section:
  - Remove the `ANTHROPIC_API_KEY=` block
  - Add `GEMINI_API_KEY=`, `GEMINI_MODEL=gemini-2.5-flash` (with comment: "default model, overridable"), `MOCK_LLM=false`
- Orchestrator-Specific Rules section:
  - `**No Claude calls outside `claude_client.py`**` → `**No LLM calls outside `llm_client.py`** — all google-genai SDK usage is centralized there.`
  - Temperature rule: unchanged (still `0.1`)
- Common Mistakes to Avoid section: update the bullet `LLM call inside an MCP server` wording to be provider-agnostic (if it references Claude specifically)

### `docs/architecture.md`

- Line ~12: `Claude Sonnet (Anthropic) as the sole LLM ...` → `Gemini (Google) as the sole LLM — strong structured output support, configurable model via GEMINI_MODEL`
- Lines ~99-100: `Claude Sonnet (Anthropic API) — reasoning & summarization` → `Gemini (Google google-genai SDK) — reasoning & summarization`. Keep the `Temperature: 0.1 (fixed)` line.

### `docs/specs/spec-agent-orchestrator.md`

- Line ~13: `implemented as a **Claude tool-use loop**` → `implemented as a **directed LLM pipeline** — the orchestrator sequences stages and tells the LLM exactly what to analyze at each step`
- Line ~15: remove "Claude's native tool-use is sufficient and simpler to debug" — rationale no longer applies. Replace with a short note: "The LLM is called per-stage with a schema-bound prompt; no agentic tool-use loop."
- Lines ~59, ~92: `Claude reads...` / `Claude scores...` → `The LLM reads...` / `The LLM scores...`
- Section 2.2 (token budget): update numbers only if Slice 2 or Slice 5 caused meaningful drift. Otherwise leave.
- Section 6.1 / 6.2: provider-agnostic wording.
- Line ~529: `claude_client.py       # Thin wrapper around Anthropic SDK` → `llm_client.py         # Thin wrapper around google-genai SDK`

### `docs/specs/spec-api.md`

- Lines ~605-606: `# Anthropic (passed to orchestrator)` / `ANTHROPIC_API_KEY: str    # required, no default` → `# Gemini (passed to orchestrator)` / `GEMINI_API_KEY: str    # required, no default` / `GEMINI_MODEL: str = "gemini-2.5-flash"`

### `STATUS.md`

- Add a new Phase entry at the top of the Phase log:
  ```
  ## Phase N — Anthropic → Gemini migration

  Migrated orchestrator LLM from Anthropic Claude Sonnet to Google Gemini.
  Model configurable via GEMINI_MODEL (default: gemini-2.5-flash).
  See docs/migrations/gemini/ for the slice breakdown.
  ```
- Line ~227 (the `apps/api/orchestrator/claude_client.py` reference): leave as historical record of what was extracted in Phase 3A/B, but add a follow-up note: `(renamed to llm_client.py in Gemini migration)`. Do not rewrite history.

### `ROADMAP.md`

- Line ~3 ("100% agent-driven via Claude Code in VS Code"): unchanged. This refers to the editing tool, not the app's LLM.
- Any other Claude/Anthropic references in the roadmap: update to provider-agnostic wording.

### Grep sweep — final pass

After all edits, these should return zero hits (except intentional historical references):
- `rg -i 'anthropic' --glob '!docs/migrations/**'`
- `rg 'claude_client' --glob '!docs/migrations/**' --glob '!STATUS.md'`
- `rg 'MOCK_CLAUDE'`
- `rg 'call_claude'`

`docs/migrations/**` is excluded because it contains the historical migration record (this folder). `STATUS.md` may retain one historical reference per the instruction above.

## Acceptance criteria

- [ ] All grep sweeps above return only intentional hits
- [ ] `CLAUDE.md` env var table exactly matches the keys declared in `apps/api/config.py`
- [ ] `CLAUDE.md` tech stack row mentions Gemini, not Claude
- [ ] The "No LLM calls outside `llm_client.py`" rule is present and worded as above
- [ ] `STATUS.md` has a new Phase entry for the migration
- [ ] `docs/architecture.md` and both spec files are provider-agnostic except where they intentionally name Gemini
- [ ] The `CLAUDE.md` filename itself is unchanged

## Out of scope (deferred)

- Renaming `CLAUDE.md` itself — out of scope; see README.md for rationale
- Reorganizing `docs/specs/` structure
- Adding a migration-history section to the top-level README

## Manual steps

None. Pure doc change.

## Rollback

Revert the single commit. No code behavior is affected.

## Definition of migration done

After Slice 7 lands:

- [ ] Branch `claude/evaluate-gemini-api-2PruJ` has 7 slice commits
- [ ] All acceptance criteria across slices pass
- [ ] One full prod deploy on Gemini has run successfully (Slice 4 post-deploy checklist)
- [ ] Old Anthropic secrets revoked and deleted (Slice 4 post-deploy checklist)
- [ ] Branch is ready to merge to `main`
