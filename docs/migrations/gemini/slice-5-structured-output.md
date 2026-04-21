# Slice 5 — Structured output

## Goal

Use Gemini's native JSON schema enforcement (`response_mime_type="application/json"` + `response_schema=<pydantic model>`) on the four schema-bound stages. Reduce retry-on-schema-failure noise and make the client smaller.

## Context

The current architecture (post-Slice 2) tells the LLM "No prose. No markdown. Start with `{`" and catches schema failures with a 3-attempt retry loop in each stage. Gemini supports native structured output that is stronger than prompt-only instruction. This slice opts the four JSON stages into it.

The `follow_up` stage returns plain text and is unaffected.

## Changes

### `apps/api/orchestrator/llm_client.py`

Add an optional parameter to `call_llm`:
```python
async def call_llm(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4000,
    response_schema: type[BaseModel] | None = None,
) -> str:
```

When `response_schema` is provided, set on the `GenerateContentConfig`:
- `response_mime_type="application/json"`
- `response_schema=response_schema`

When `None`, behavior is unchanged (prompt-only, plain text).

Do NOT remove the markdown-fence stripping in `parse_json_response()` — keep it as a safety net. Gemini can still wrap output in fences occasionally despite JSON mode.

### Stage call sites — pass the schema

- `apps/api/orchestrator/stages/intake.py` — pass `IntakeResult`
- `apps/api/orchestrator/stages/measure_analyst.py` — pass `MeasureAnalysis`
- `apps/api/orchestrator/stages/candidate_analyst.py` — pass `CandidateAnalysis`
- `apps/api/orchestrator/stages/relevance_ranker.py` — pass schema for `list[RelevanceScore]`

**Array-response edge case:** the `relevance_ranker` prompt asks for a JSON array, not an object. Test whether `google-genai` accepts `list[RelevanceScore]` directly as `response_schema`. If not, either:
- (a) wrap in an object schema (e.g. `class RelevanceRanking(BaseModel): scores: list[RelevanceScore]`) and update the prompt to produce `{"scores": [...]}`, OR
- (b) leave `relevance_ranker` on prompt-only mode and add a `# FUTURE:` comment pointing at this section.

Decide during implementation based on what the SDK supports. Prefer (a) if it works cleanly.

### Retry logic — leave alone for now

Keep the 3-attempt retry in each stage. Slice 6 decides whether to lower it based on telemetry.

### Prompt files — no changes

The prompt `.txt` files already produce valid JSON structure; keep them as-is so Gemini's structured-output enforcement is purely additive.

## Acceptance criteria

- [ ] `call_llm` accepts `response_schema=None` (default) and behaves exactly as in Slice 2
- [ ] `call_llm` accepts `response_schema=<BaseModel>` and returns schema-valid JSON as a string
- [ ] All 4 JSON-producing stages pass their schemas through
- [ ] Full test suite passes, including schema-mismatch retry tests (use a mock that returns bad JSON to verify retry still fires)
- [ ] Mock mode unaffected (`MOCK_LLM=true` still returns the fixture without calling the API)
- [ ] Markdown-fence stripping still runs (kept as safety net)
- [ ] If `relevance_ranker` takes the wrap-in-object path, its prompt is updated to match the new schema shape

## Out of scope (deferred)

- Lowering retry counts — Slice 6, data-driven decision
- Removing fence-stripping — not in scope for this migration; too risky
- Adding JSON mode to `follow_up` — it returns plain text by design

## Manual steps

None. Pure code change.

## Rollback

Revert the single commit. Stages fall back to prompt-only JSON instruction, which is what Slice 2 already proved works.
