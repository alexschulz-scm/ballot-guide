# Build Prompt: Agent Orchestrator

**Component:** `apps/api/orchestrator/`  
**Spec:** `docs/specs/spec-agent-orchestrator.md`  
**Depends on:** MCP Servers built and tests passing  
**Estimated sessions:** 4 focused sessions  

---

## ⚠️ Before Anything Else

Read these files in order before responding:
1. `CLAUDE.md` (repo root)
2. `docs/specs/spec-mcp-servers.md` (what tools are available to the orchestrator)
3. `docs/specs/spec-agent-orchestrator.md`
4. `docs/neutrality-contract.md`

Do not write any code. Confirm you have read all four files by answering:
- What are the 5 stages of the orchestrator and what does each do?
- What is the difference between directed tool-use and autonomous tool-use, and which does this project use?
- Name 3 things the orchestrator is explicitly NOT allowed to add to any output schema.

---

## PHASE 1 — PLANNING

*No code. Planning output only. Stop at the gate.*

### Step 1: File inventory

List every file you will create, with one sentence describing its purpose. Organize by session (A, B, C, D). For each file state: does it call Claude? Does it call MCP tools? Does it define schemas?

### Step 2: Schema review

Read Section 3 of the spec (Output Schemas). For each schema, answer:
- Which stage produces it?
- Which stage(s) consume it?
- What happens if a required field is missing?

Draw the data flow: `IntakeResult → BallotFoundEvent → MeasureAnalysis[] → RelevanceScore[] → BallotReport`

### Step 3: Prompt file plan

List the 5 prompt files that must be created in `apps/api/orchestrator/prompts/`. For each one:
- What data does it receive as input (the `{variables}`)?
- What schema must it produce as output?
- What is the single most important neutrality rule it must enforce?

### Step 4: Retry logic plan

Describe the retry strategy from Section 6.2 in your own words. Then describe exactly how you will test it — what mock will you inject to simulate Claude returning bad JSON?

### Step 5: Risk identification

Identify the 3 most likely failure modes during implementation (not at runtime — during the build). For each:
- What is the risk?
- How will you detect it early?
- What guardrail prevents it?

### ✋ STOP HERE
Present plan. Wait for approval before writing any code.

---

## PHASE 2 — BUILD

*Execute in Claude Code (VS Code) after plan approval.*  
*Complete sessions in order. Run tests at end of each session before proceeding.*

---

### Session A: Schemas and Events

**Goal:** Define all data contracts before any logic is written. Everything else in the orchestrator depends on these being correct and stable.

**Rule:** This session creates NO logic files. Only schema definitions.

#### Task A1: Output Schemas

Create `apps/api/orchestrator/schemas.py`.

Must define exactly these classes (names must match exactly — other files import by name):
- `IntakeResult`
- `MeasureAnalysis`
- `RaceAnalysis`
- `CandidateAnalysis`
- `RelevanceScore`
- `BallotReport`
- `BallotReportItem`
- `SourceCitation`

All field definitions are in `spec-agent-orchestrator.md` Section 3. Copy them exactly. Do not add fields. Do not remove fields. Do not rename fields.

**Critical field to double-check:**  
`BallotReport` must NOT have any of these fields: `recommendation`, `suggested_vote`, `lean`, `preferred_candidate`, `vote_for`. If you find yourself adding any of these, stop and re-read the neutrality contract.

**Acceptance check — run this before moving on:**
```python
from apps.api.orchestrator.schemas import (
    IntakeResult, MeasureAnalysis, RaceAnalysis,
    RelevanceScore, BallotReport, SourceCitation
)

# Verify BallotReport has no recommendation fields
import inspect
report_fields = BallotReport.model_fields.keys()
forbidden = {'recommendation', 'suggested_vote', 'lean', 'preferred'}
assert len(forbidden & set(report_fields)) == 0, f"Forbidden fields found: {forbidden & set(report_fields)}"
print("Schema check passed")
```

---

#### Task A2: Event Models

Create `apps/api/orchestrator/events.py`.

Must define exactly these classes:
- `OrchestratorEvent` (base)
- `IntakeCompleteEvent`
- `ClarificationNeededEvent`
- `BallotFoundEvent`
- `ItemAnalyzedEvent`
- `RankingCompleteEvent`
- `ReportCompleteEvent`
- `ErrorEvent`

All definitions are in `spec-agent-orchestrator.md` Section 4.

Each event must have `event_type` as a `Literal` string — not a free-form string. This prevents the API layer from receiving events with typos in the type field.

**Acceptance check:**
```python
from apps.api.orchestrator.events import (
    IntakeCompleteEvent, ReportCompleteEvent, ErrorEvent
)
from datetime import datetime

e = IntakeCompleteEvent(
    session_id="test-123",
    timestamp=datetime.utcnow().isoformat(),
    zip_code="33101",
    priorities=["housing"],
    display_name=None
)
assert e.event_type == "intake_complete"
print("Events check passed")
```

---

#### Task A3: Session A Tests

Create `tests/orchestrator/test_schemas.py`.

Required tests:
```
test_intake_result_rejects_unknown_priority_topic
test_intake_result_max_5_priorities_enforced
test_measure_analysis_requires_sources
test_ballot_report_has_no_recommendation_field
test_relevance_score_is_1_to_10
test_source_citation_requires_url
test_all_events_have_event_type_literal
test_report_complete_event_contains_ballot_report
```

Run: `pytest tests/orchestrator/test_schemas.py -v`  
All must pass.

---

### Session B: Claude Client and Prompt Files

**Goal:** The thin wrapper around the Anthropic SDK, and all 5 prompt files.  
**Rule:** No stage logic yet. Just the client and prompts.

#### Task B1: Claude Client

Create `apps/api/orchestrator/claude_client.py`.

Must implement exactly:

```python
async def call_claude(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4000,
    temperature: float = 0.1   # low temperature for consistency
) -> str:
    """
    Calls Claude Sonnet via Anthropic SDK.
    Returns the text content of Claude's response.
    Raises ClaudeError on API failure (never raises raw Anthropic exceptions).
    Logs token usage to structured logger.
    """

async def parse_json_response(
    response_text: str,
    schema: type[BaseModel]
) -> BaseModel:
    """
    Parses Claude's response text as JSON and validates against schema.
    Strips markdown code fences if present (```json ... ```).
    Raises SchemaValidationError with the validation details if invalid.
    Never raises raw Pydantic ValidationError — always wraps it.
    """

def load_prompt(prompt_name: str) -> str:
    """
    Loads prompt text from apps/api/orchestrator/prompts/{prompt_name}.txt
    Raises FileNotFoundError if prompt doesn't exist.
    """
```

**Critical:** `call_claude` must check for `MOCK_CLAUDE=true` environment variable. If set, return the content of `tests/fixtures/claude/{mock_response_file}` instead of calling the API. The mock file name is passed as a parameter when testing.

Temperature must be 0.1 — not configurable per call. Low temperature = more consistent JSON output = fewer retries.

---

#### Task B2: Prompt Files

Create these 5 files exactly as specified in `spec-agent-orchestrator.md` Section 5.2:

```
apps/api/orchestrator/prompts/system.txt
apps/api/orchestrator/prompts/intake.txt
apps/api/orchestrator/prompts/measure_analysis.txt
apps/api/orchestrator/prompts/candidate_analysis.txt
apps/api/orchestrator/prompts/relevance_ranking.txt
```

Copy the prompt content from the spec exactly.

Then add one additional section to EACH prompt file (except system.txt):

```
OUTPUT FORMAT:
Return ONLY valid JSON matching the schema below. 
No prose. No markdown. No code fences. No explanation.
Start your response with { and end with }.

Schema:
{paste the relevant Pydantic schema here as a JSON example}
```

This explicit output format instruction is the single most effective way to reduce malformed JSON from cheaper models.

**After creating all files, verify:**
```bash
ls apps/api/orchestrator/prompts/
# Should show: system.txt intake.txt measure_analysis.txt 
#              candidate_analysis.txt relevance_ranking.txt
```

---

#### Task B3: Session B Tests

Create `tests/orchestrator/test_claude_client.py`.

Required tests:
```
test_call_claude_uses_mock_when_env_set
test_parse_json_response_valid_json_returns_model
test_parse_json_response_strips_markdown_fences
test_parse_json_response_invalid_json_raises_schema_validation_error
test_parse_json_response_missing_required_field_raises_error
test_load_prompt_returns_file_contents
test_load_prompt_raises_on_missing_file
test_call_claude_logs_token_usage
```

All tests must use `MOCK_CLAUDE=true` — no real API calls.

---

### Session C: Stage Implementations

**Goal:** Implement all 5 stages.  
**Rule:** Each stage is its own file. Stages never call each other. All sequencing is in `runner.py` (Session D).

#### Task C1: Intake Stage

Create `apps/api/orchestrator/stages/intake.py`.

```python
async def run_intake(
    message: str,
    history: list[dict],
    db_path: str
) -> IntakeResult:
    """
    Stage 1: Extract zip code and priorities from user message.
    Loads intake.txt prompt, calls Claude, parses IntakeResult.
    Saves zip_code, priorities, display_name to session in SQLite.
    Returns IntakeResult.
    """
```

Normalization rules (enforced in this function, not left to Claude):
- After Claude returns IntakeResult, validate all priority values are in canonical taxonomy
- Replace any non-taxonomy values with closest match OR drop them
- Truncate priorities list to max 5
- Normalize zip_code to exactly 5 digits (strip spaces, validate format)

---

#### Task C2: Ballot Resolver Stage

Create `apps/api/orchestrator/stages/ballot_resolver.py`.

```python
async def run_ballot_resolver(
    zip_code: str,
    election_id: str | None,
    db_path: str
) -> BallotFoundEvent | ErrorEvent:
    """
    Stage 2: Resolve zip code to ballot.
    Calls MCP tool: get_ballot_by_address.
    Returns BallotFoundEvent on success.
    Returns ErrorEvent on ToolError (no exceptions raised).
    Saves ballot_id to session in SQLite.
    """
```

---

#### Task C3: Measure Analyst Stage

Create `apps/api/orchestrator/stages/measure_analyst.py`.

```python
async def run_measure_analysis(
    measure_summary: MeasureSummary,
    user_priorities: list[str],
    db_path: str
) -> MeasureAnalysis | None:
    """
    Stage 3a: Analyze one ballot measure.
    Calls MCP tools: get_measure_detail, get_measure_text, 
                     parse_measure_text, search_news.
    Calls Claude with measure_analysis.txt prompt.
    Returns MeasureAnalysis on success.
    Returns None on failure (caller handles gracefully).
    Retries Claude call up to 2 times on schema validation failure.
    """
```

**Retry implementation — must match spec exactly:**
```python
for attempt in range(3):
    try:
        response = await call_claude(...)
        result = await parse_json_response(response, MeasureAnalysis)
        return result
    except SchemaValidationError as e:
        if attempt == 2:
            logger.error(f"All retries failed for measure {measure_id}: {e}")
            return None
        retry_message = f"Your response had this error: {e}. Return valid JSON."
        # add to messages and retry
```

---

#### Task C4: Candidate Analyst Stage

Create `apps/api/orchestrator/stages/candidate_analyst.py`.

```python
async def run_candidate_analysis(
    candidate_ids: list[str],
    user_priorities: list[str],
    race_id: str,
    db_path: str
) -> RaceAnalysis | None:
    """
    Stage 3b: Analyze all candidates in one race.
    For each candidate_id:
      Calls MCP tools: get_candidate_detail, get_campaign_finance, search_news
      Calls Claude with candidate_analysis.txt prompt → CandidateAnalysis
    Assembles RaceAnalysis from all CandidateAnalysis results.
    Returns RaceAnalysis on success.
    Returns None if all candidates fail.
    """
```

---

#### Task C5: Relevance Ranker Stage

Create `apps/api/orchestrator/stages/relevance_ranker.py`.

```python
async def run_relevance_ranking(
    measures: list[MeasureAnalysis],
    races: list[RaceAnalysis],
    user_priorities: list[str]
) -> list[RelevanceScore]:
    """
    Stage 4: Score all items against user priorities.
    Calls Claude with relevance_ranking.txt prompt.
    Returns list of RelevanceScore, one per measure + race.
    List is sorted by relevance_score descending before returning.
    
    Post-processing (after Claude, before return):
    - Scan all relevance_reason strings for forbidden language
    - Forbidden words in outcome-preference context: 
      "help you", "benefit you", "support your goal", "align with your values",
      "better for you", "improve your"
    - If found, replace with: "[relevance reason unavailable]" and log warning
    """
```

The forbidden language scan is deterministic Python string matching — not another Claude call. Fast, free, auditable.

---

#### Task C6: Report Assembler Stage

Create `apps/api/orchestrator/stages/report_assembler.py`.

```python
def assemble_report(
    session_id: str,
    election: ElectionSummary,
    precinct: PrecinctInfo,
    user_priorities: list[str],
    measures: list[MeasureAnalysis],
    races: list[RaceAnalysis],
    scores: list[RelevanceScore]
) -> BallotReport:
    """
    Stage 5: Assemble the final BallotReport.
    Pure function — no Claude calls, no MCP calls, no I/O.
    Joins measures/races with their relevance scores.
    Sorts items by relevance_score descending.
    Returns BallotReport.
    """
```

This is deliberately a sync pure function — no async, no external calls. Report assembly is deterministic data joining. If you find yourself adding a Claude call here, stop — that logic belongs in an earlier stage.

---

#### Task C7: Session C Tests

Create `tests/orchestrator/test_stages.py`.

Required tests (all use mocked Claude + mocked MCP):
```
test_intake_normalizes_free_text_priority
test_intake_truncates_to_5_priorities
test_intake_invalid_zip_sets_needs_clarification
test_ballot_resolver_returns_error_event_on_mcp_failure
test_measure_analyst_retries_on_bad_json
test_measure_analyst_returns_none_after_3_failures
test_measure_analyst_always_has_both_arguments
test_candidate_analyst_assembles_race_from_candidates
test_relevance_ranker_removes_outcome_preference_language
test_relevance_ranker_sorts_by_score_descending
test_report_assembler_is_pure_function (no async, no mocks needed)
test_report_assembler_items_ordered_by_score
```

---

### Session D: Runner and End-to-End

**Goal:** Wire all stages into the orchestrator runner. End-to-end test against FL 2022 seed data.

#### Task D1: Runner

Create `apps/api/orchestrator/runner.py`.

```python
async def run_orchestrator(
    session_id: str,
    message: str,
    db_path: str
) -> AsyncGenerator[OrchestratorEvent, None]:
    """
    Entry point. Sequences all 5 stages.
    Yields OrchestratorEvent objects as stages complete.
    Never raises exceptions — yields ErrorEvent instead.
    Saves final report to sessions.report_json in SQLite.
    """
```

**Exact sequence (do not reorder):**
```python
# 1. Load session history from SQLite
# 2. Run Stage 1: Intake
#    yield IntakeCompleteEvent
#    if needs_clarification: yield ClarificationNeededEvent, return
# 3. Run Stage 2: Ballot Resolution  
#    yield BallotFoundEvent
#    if ErrorEvent: yield it, return
# 4. Run Stage 3: Item Analysis (measures first, then races)
#    for each item: yield ItemAnalyzedEvent as completed
# 5. Run Stage 4: Relevance Ranking
#    yield RankingCompleteEvent
# 6. Run Stage 5: Report Assembly
#    yield ReportCompleteEvent
# 7. Save report to SQLite
# 8. Save messages to SQLite
```

---

#### Task D2: End-to-End Test

Create `tests/orchestrator/test_runner.py`.

Required tests:
```
test_full_run_fl2022_produces_valid_report
test_full_run_yields_all_required_events_in_order
test_full_run_clarification_stops_after_intake
test_full_run_partial_report_when_one_measure_fails
test_full_run_report_items_ordered_by_relevance
test_full_run_no_recommendation_in_output
test_full_run_completes_within_90_seconds (use FL 2022 seed, mock Claude fast)
```

For `test_full_run_fl2022_produces_valid_report`:
- Load FL 2022 General seed data
- Mock all MCP tool calls to return seed data
- Mock Claude to return pre-written valid fixtures
- Run full orchestrator
- Assert `BallotReport` is valid, has ≥ 4 measures, ≥ 2 races

---

## Final Verification

```bash
pytest tests/orchestrator/ -v --tb=short
```

All tests pass. Then run the Definition of Done checklist from `spec-agent-orchestrator.md` Section 9.

**Additional manual check before marking done:**
Read 5 `relevance_reason` strings from the test output. Ask yourself: "Does this tell the user what to think, or does it describe a topic connection?" If any feel directional, add them to the forbidden language list in `relevance_ranker.py` and add a test.

---

## If You Get Stuck

**"Claude keeps returning prose instead of JSON"**  
→ Add the OUTPUT FORMAT block from Task B2 to the prompt. Use a stricter prefix: "Return ONLY a JSON object. Your entire response must start with { and end with }."

**"Schema validation keeps failing on retry"**  
→ Add `print(response_text[:500])` before the parse attempt to see what Claude actually returned. The issue is almost always: extra prose before the JSON, or a field name mismatch.

**"The relevance_reason forbidden language scan has false positives"**  
→ Make the check more specific. "help" alone is too broad. Check for "help you" or "help with your" as phrases. Test with real examples before tightening.

**"Runner test is slow because of sequential Claude calls"**  
→ This is expected. Use the `MOCK_CLAUDE=true` env var in all tests. Real timing only matters in the 90-second performance test.

**"I'm not sure if a field belongs in MeasureAnalysis or BallotReportItem"**  
→ Rule: data about the measure itself → `MeasureAnalysis`. Data about how it relates to this user → `BallotReportItem` (relevance_score, relevance_reason, matched_priorities).

**"A stage needs to call another stage"**  
→ It doesn't. Stop. Re-read the spec. All sequencing is in `runner.py`. If stage B needs data from stage A, `runner.py` passes it as a parameter to stage B.
