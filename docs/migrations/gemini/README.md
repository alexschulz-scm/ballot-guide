# Anthropic → Gemini Migration

Work slices for replacing the Anthropic Claude API with Google's Gemini API as the orchestrator's LLM.

Branch: `claude/evaluate-gemini-api-2PruJ`

## Decisions

- **Model:** configurable via `GEMINI_MODEL` env var. Default `gemini-2.5-flash`.
- **Structured output (Gemini JSON mode):** in scope. See Slice 5.
- **Public API renames:** `call_claude` → `call_llm`, `ClaudeError` → `LLMError`, `claude_client.py` → `llm_client.py`.
- **`CLAUDE.md` filename stays** — it's context for Claude Code (the editing tool), not the app's LLM. Its content gets updated in Slice 7.
- **Manual deploy steps (secret rotation)** live in the slice file that needs them (Slice 4), as a checklist. Plan/implement cycle for Slice 4 pauses for user confirmation before merging.

## Slices

| # | Name | Risk | Depends on |
|---|---|---|---|
| 1 | [Config scaffolding](./slice-1-config-scaffolding.md) | low | — |
| 2 | [LLM client swap](./slice-2-llm-client-swap.md) | medium | 1 |
| 3 | [Decommission Anthropic](./slice-3-decommission-anthropic.md) | low | 2 |
| 4 | [Infra & CI](./slice-4-infra-and-ci.md) | medium (deploy) | 3 |
| 5 | [Structured output](./slice-5-structured-output.md) | low | 2 |
| 6 | [Prompt validation](./slice-6-prompt-validation.md) | medium (behavior) | 5 |
| 7 | [Docs & rules](./slice-7-docs-and-rules.md) | low | 6 |

## Dependency graph

```
1 → 2 → 3 → 4
        ↓
        5 → 6 → 7
```

Slices 3 and 5 both depend on 2 but are independent of each other; they can ship in either order. The graph above reflects the recommended order (infra/cleanup first, behavior upgrade second).

## Workflow

For each slice:

1. User runs plan cycle with the slice file as input.
2. User runs implement cycle.
3. Slice lands as a single commit on the migration branch.
4. Acceptance criteria in the slice file must pass before moving to the next.

The whole migration ships as one branch, not seven PRs.

## Out-of-scope for this migration

- Changing the orchestrator's stage structure or retry logic
- Adding new LLM providers beyond Gemini (no abstraction layer for multi-provider)
- Frontend changes
- MCP server changes
- Database schema changes
