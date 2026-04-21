# Slice 6 — Prompt validation

## Goal

Confirm that neutrality and structural rules still hold on Gemini. Tune prompts if not. Capture a small set of golden-output fixtures for regression.

## Context

The prompts in `apps/api/orchestrator/prompts/` were tuned against Claude. Even with identical inputs, Gemini may drift toward:
- recommendations ("you should vote for…")
- "helpful" phrasing that violates the forbidden-phrase list
- unbalanced measure analyses (proponent-heavy or opponent-heavy)
- dropped source citations

This slice is the only defense against silent behavior regressions. **Do not skip.**

## Changes

### New: `tests/orchestrator/test_neutrality.py`

An end-to-end test that runs `runner.py` against seed data and asserts:

- No forbidden output fields anywhere in the assembled report: `recommendation`, `suggested_vote`, `lean`, `preferred_candidate`, `vote_for`
- No forbidden `relevance_reason` phrases (the six phrases enforced in `relevance_ranker.py` lines 16-23): "help you", "benefit you", "support your goal", "align with your values", "better for you", "improve your"
- Every measure in `report.measures` has both `proponent_argument` and `opponent_argument` non-empty
- Every `candidate` entry has a non-empty `sources` list
- Every `measure` entry has a non-empty `sources` list

Mark with `@pytest.mark.neutrality` so it can be run in isolation. Wire into the default `pytest` run.

### Prompt tuning (only if tests fail)

If the neutrality test fails on seed data, edit only these files:
- `apps/api/orchestrator/prompts/system.txt` — first lever; tighten neutrality rules
- The specific stage prompt whose output fails (e.g., `measure_analysis.txt` if arguments go unbalanced)

Do NOT change Python code in this slice. If a fix requires code, stop and reopen Slice 2 or Slice 5 for the fix.

### Golden fixtures

Save one full report per seed ballot to `tests/fixtures/llm/golden/` as JSON. Structure:
```
tests/fixtures/llm/golden/
├── ballot-001.json    # full assembled report
├── ballot-002.json
└── ...
```

Add a lightweight regression test that loads each golden file and re-runs the neutrality assertions against it. This detects future drift even without re-calling the live API.

### Retry count telemetry review

Run the full pipeline once against seed data with `MOCK_LLM=false` and a real `GEMINI_API_KEY`. Check the logs for `SchemaValidationError` counts. If schema-failure retries are consistently 0-1 per stage, consider a follow-up slice to lower the retry cap from 3 → 2. Do NOT change it in this slice — capture a note in the implement cycle's summary instead.

## Acceptance criteria

- [ ] `pytest -m neutrality` passes against seed data (with real `GEMINI_API_KEY`)
- [ ] Golden fixtures exist for every seed ballot
- [ ] Golden-fixture regression test passes
- [ ] Any prompt changes are scoped to `.txt` files in `apps/api/orchestrator/prompts/` — no Python changes
- [ ] Implement cycle summary notes observed retry counts per stage

## Out of scope (deferred)

- Lowering retry counts — follow-up slice if data warrants it
- Regenerating goldens on every run — they are a baseline, not a contract
- Adding more neutrality rules beyond what `CLAUDE.md` already forbids
- Performance / latency tuning

## Manual steps

- Obtain a `GEMINI_API_KEY` for the validation run (can be the same personal key from Slice 2).
- Budget for one full run of the orchestrator against all seed ballots — expect real API spend in the low single-digit cents.

## Rollback

Revert the single commit. If the neutrality test fails and prompt tuning was attempted, the revert removes both the test and the prompt edits together — back to Slice 5 baseline.
