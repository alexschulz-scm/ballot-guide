# Ballot Guide — Development Roadmap

**Development mode:** 100% agent-driven via Claude Code in VS Code  
**Live project status:** `STATUS.md` ← agents read and update this  
**Rule:** Agents never modify `ROADMAP.md`. Agents maintain `STATUS.md`.

## How to Use

**You:** Open `STATUS.md`, find the next incomplete session, copy the starter prompt into Claude Code. When gate commands pass, confirm with the agent to update `STATUS.md`.

**The agent:** Read `STATUS.md` first every session. Update it at the end. Never touch this file.

## Phase Overview

| Phase | Component | Sessions |
|-------|-----------|----------|
| 1 | Database (Spec 4) | 2 |
| 2 | MCP Servers (Spec 1) | 3 |
| 3 | Orchestrator (Spec 2) | 3 |
| 4 | API Layer (Spec 3) | 3 |
| 5 | Frontend (Spec 5) | 4 |
| **Total** | | **15** |

Each phase must fully pass its gate before the next begins.

---

## Phase 1 — Database

**Spec:** `docs/specs/spec-database.md`  
**Prompt:** `docs/prompts/prompt-database.md`  
**Output:** `apps/api/db/`, `data/seed/`, `scripts/`

### Session 1-A — Schema, Migrations, SQLite Config

**Milestone ID:** `1A`

**Files to open:**
- `CLAUDE.md`
- `docs/INTEGRATION_REVIEW.md`
- `docs/specs/spec-database.md`
- `docs/prompts/prompt-database.md`

**Starter prompt:**
```
Read these files in order before doing anything else:
1. CLAUDE.md
2. docs/INTEGRATION_REVIEW.md
3. docs/specs/spec-database.md — full read
4. docs/prompts/prompt-database.md — planning questions + Session A only

Before writing any code, output your answers to the 5 planning questions.
Wait for my confirmation before proceeding to code.
```

**Builds:**
- `apps/api/db/migrations/001_initial.sql` — full schema + 7 indexes
- `apps/api/db/migrations/002_seed_fl_2022.sql`
- `apps/api/db/connection.py` — migration runner, WAL config, `get_db()`
- `apps/api/db/__init__.py`
- `tests/db/test_schema.py`

**Gate:**
```bash
cd apps/api
python -c "import asyncio; from db.connection import run_migrations; asyncio.run(run_migrations(':memory:'))"
# Expect: Applied migration: 001_initial.sql / 002_seed_fl_2022.sql

python -m pytest tests/db/test_schema.py -v
# Must pass: test_fresh_db_has_all_8_tables, test_fresh_db_has_all_7_indexes,
#            test_migrations_idempotent, test_wal_mode_enabled,
#            test_foreign_keys_cascade_delete
```

---

### Session 1-B — Seed Data and Query Functions

**Milestone ID:** `1B`  
**Depends on:** `1A` gate passed

**Files to open:**
- `STATUS.md` ← confirm 1A complete
- `CLAUDE.md`
- `docs/specs/spec-database.md` (Sections 5, 6, 7)
- `docs/prompts/prompt-database.md` (Session B only)

**Starter prompt:**
```
Read STATUS.md — confirm 1A is marked complete before proceeding.

Then read:
- CLAUDE.md
- docs/specs/spec-database.md (Sections 5, 6, 7)
- docs/prompts/prompt-database.md (Session B only)

Execute Session B. When done, update STATUS.md: mark 1B complete, list files created.
```

**Builds:**
- `data/seed/README.md`, `fl_2022_election.json`, `fl_2022_measures.json`, `fl_2022_candidates.json`
- `scripts/seed_historical.py` — `--replace` and `--dry-run` flags
- `apps/api/db/queries.py` — 6 canonical query functions including `get_session` JOIN
- `apps/api/db/versioning.py` — `compute_data_version()`, `check_data_freshness()`
- `tests/db/test_queries.py`, `test_versioning.py`, `test_seed.py`

**Gate:**
```bash
python scripts/seed_historical.py --db /tmp/test.db --dry-run
python scripts/seed_historical.py --db /tmp/test.db
python -m pytest tests/db/ -v
# Must pass: test_fl_2022_has_4_amendments, test_get_session_returns_election_name,
#            test_compute_data_version_deterministic, test_replace_flag_atomic
rm /tmp/test.db
```

**Phase 1 complete gate:** `python -m pytest tests/db/ -v --tb=short` — Zero failures.

---

## Phase 2 — MCP Servers

**Spec:** `docs/specs/spec-mcp-servers.md`  
**Prompt:** `docs/prompts/prompt-mcp-servers.md`  
**Output:** `mcp-servers/`  
**Depends on:** Phase 1 gate passed

### Session 2-A — ballot-data-mcp: Foundation and Cache

**Milestone ID:** `2A`

**Files to open:**
- `STATUS.md` ← confirm Phase 1 complete
- `CLAUDE.md`, `docs/INTEGRATION_REVIEW.md`
- `docs/specs/spec-mcp-servers.md` (Sections 1–3.1)
- `docs/prompts/prompt-mcp-servers.md` (Session A only)

**Starter prompt:**
```
Read STATUS.md — confirm Phase 1 complete.

Then read:
- CLAUDE.md
- docs/INTEGRATION_REVIEW.md (Issue 2 — SourceCitation replaces DataSource everywhere)
- docs/specs/spec-mcp-servers.md (Sections 1-3.1)
- docs/prompts/prompt-mcp-servers.md (Session A only)

Execute Session A. Update STATUS.md when done.
```

**Builds:** `mcp-servers/shared/models.py`, `ballot_data/server.py`, `ballot_data/cache.py`, `ballot_data/tools/get_ballot_by_address.py`, tests.

**Gate:**
```bash
MOCK_EXTERNAL_APIS=true python -m pytest tests/mcp/test_ballot_cache.py tests/mcp/test_get_ballot.py -v
# Must pass: test_cache_hit_skips_external_call, test_out_of_state_returns_error
```

---

### Session 2-B — ballot-data-mcp: Remaining Tools

**Milestone ID:** `2B`  
**Depends on:** `2A`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-mcp-servers.md` (Sections 3.2–3.4), `prompt-mcp-servers.md` (Session B only)

**Starter prompt:**
```
Read STATUS.md — confirm 2A complete.
Read: CLAUDE.md, docs/specs/spec-mcp-servers.md (3.2-3.4),
      docs/prompts/prompt-mcp-servers.md (Session B only)
Execute Session B. Update STATUS.md when done.
```

**Builds:** `get_measure_detail.py`, `get_candidate_detail.py`, `get_campaign_finance.py`, tests.

**Gate:**
```bash
MOCK_EXTERNAL_APIS=true python -m pytest tests/mcp/ -v --tb=short
# Must pass: test_positions_flattening_works, test_top_donors_formatted_correctly
```

---

### Session 2-C — legislation-mcp and news-mcp

**Milestone ID:** `2C`  
**Depends on:** `2B`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-mcp-servers.md` (Sections 4–5), `prompt-mcp-servers.md` (Session C only)

**Starter prompt:**
```
Read STATUS.md — confirm 2B complete.
Read: CLAUDE.md, docs/specs/spec-mcp-servers.md (4-5),
      docs/prompts/prompt-mcp-servers.md (Session C only)
Execute Session C. Update STATUS.md when done.
```

**Builds:** Both legislation and news MCP servers with all tools, tests.

**Gate:**
```bash
MOCK_EXTERNAL_APIS=true python -m pytest tests/mcp/ -v --tb=short
# Must pass: test_parse_measure_text_no_llm. Zero failures across all 3 servers.
```

**Phase 2 complete gate:** `MOCK_EXTERNAL_APIS=true python -m pytest tests/mcp/ -v --tb=short` — Zero failures.

---

## Phase 3 — Orchestrator

**Spec:** `docs/specs/spec-agent-orchestrator.md`  
**Prompt:** `docs/prompts/prompt-agent-orchestrator.md`  
**Output:** `apps/api/orchestrator/`  
**Depends on:** Phase 2 gate passed

### Session 3-A — Schemas, Events, Claude Client, Intake

**Milestone ID:** `3A`

**Files to open:**
- `STATUS.md` ← confirm Phase 2 complete
- `CLAUDE.md`, `docs/INTEGRATION_REVIEW.md`
- `docs/specs/spec-agent-orchestrator.md` (Sections 2–5)
- `docs/prompts/prompt-agent-orchestrator.md` (Session A only)

**Starter prompt:**
```
Read STATUS.md — confirm Phase 2 complete.

Then read:
- CLAUDE.md
- docs/INTEGRATION_REVIEW.md (Issues 1, 2, 3, 4, 5, 6 all relevant)
- docs/specs/spec-agent-orchestrator.md (Sections 2-5)
- docs/prompts/prompt-agent-orchestrator.md (Session A only)

Critical from integration review:
- ElectionSummary and PrecinctInfo now defined in schemas.py — include them (Issue 1)
- DoneEvent has a timestamp field (Issue 6)
- Orchestrator writes session state via session/store.py imports, never raw SQL (Issue 5)
- SourceCitation everywhere — DataSource is retired (Issue 2)

Execute Session A. Update STATUS.md when done.
```

**Builds:** `schemas.py`, `events.py`, `claude_client.py`, `prompts/system.txt`, `prompts/intake.txt`, `stages/intake.py`, tests.

**Gate:**
```bash
MOCK_CLAUDE=true python -m pytest tests/orchestrator/test_intake.py -v
# Must pass: test_extracts_zip_and_priorities, test_needs_clarification_for_vague_address,
#            test_priorities_capped_at_5, test_taxonomy_normalization
```

---

### Session 3-B — Analysis Stages and Relevance Ranker

**Milestone ID:** `3B`  
**Depends on:** `3A`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-agent-orchestrator.md` (Sections 3, 6), `prompt-agent-orchestrator.md` (Session B only)

**Starter prompt:**
```
Read STATUS.md — confirm 3A complete.

Read:
- CLAUDE.md
- docs/specs/spec-agent-orchestrator.md (Sections 3 and 6)
- docs/prompts/prompt-agent-orchestrator.md (Session B only)

Reminders:
- CandidateAnalysis.positions is dict[str, str] — flatten CandidatePosition.summary here
- top_donors formatted "Name ($Amount)" — format DonorSummary objects here
- run_stage() retries up to 2x on Pydantic validation failure
- One item failing must NOT fail the whole report

Execute Session B. Update STATUS.md when done.
```

**Builds:** `ballot_resolver.py`, `measure_analyst.py`, `candidate_analyst.py`, `relevance_ranker.py`, 3 prompt txt files, tests.

**Gate:**
```bash
MOCK_CLAUDE=true python -m pytest tests/orchestrator/ -v \
  --ignore=tests/orchestrator/test_runner.py \
  --ignore=tests/orchestrator/test_neutrality.py
# Must pass: test_retry_on_invalid_json, test_partial_report_on_item_failure,
#            test_relevance_reason_no_outcome_language
```

---

### Session 3-C — Runner, Report Assembler, End-to-End

**Milestone ID:** `3C`  
**Depends on:** `3B`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-agent-orchestrator.md` (Sections 7–10), `prompt-agent-orchestrator.md` (Session C only)

**Starter prompt:**
```
Read STATUS.md — confirm 3B complete.
Read: CLAUDE.md, docs/specs/spec-agent-orchestrator.md (Sections 7-10),
      docs/prompts/prompt-agent-orchestrator.md (Session C only)
Execute Session C. Run Definition of Done checklist from Section 9.
Update STATUS.md when done.
```

**Builds:** `report_assembler.py`, `runner.py`, `test_runner.py`, `test_neutrality.py`.

**Gate:**
```bash
MOCK_CLAUDE=true MOCK_EXTERNAL_APIS=true python -m pytest tests/orchestrator/ -v
# Must pass: test_full_run_fl_2022_produces_valid_report, test_done_event_always_last,
#            test_all_neutrality_checks_pass

python -c "
from apps.api.orchestrator.runner import run_orchestrator
import inspect; assert inspect.isasyncgenfunction(run_orchestrator); print('OK')
"
```

**Phase 3 complete gate:** `MOCK_CLAUDE=true MOCK_EXTERNAL_APIS=true python -m pytest tests/orchestrator/ -v --tb=short` — Zero failures.

---

## Phase 4 — API Layer

**Spec:** `docs/specs/spec-api.md`  
**Prompt:** `docs/prompts/prompt-api.md`  
**Output:** `apps/api/` (routers, session store, middleware, startup)  
**Depends on:** Phase 3 gate passed

### Session 4-A — Config, Models, Session Store

**Milestone ID:** `4A`

**Files to open:**
- `STATUS.md` ← confirm Phase 3 complete
- `CLAUDE.md`, `docs/INTEGRATION_REVIEW.md`
- `docs/specs/spec-api.md` (Sections 1–3)
- `docs/prompts/prompt-api.md` (Session A only)

**Starter prompt:**
```
Read STATUS.md — confirm Phase 3 complete.

Then read:
- CLAUDE.md
- docs/INTEGRATION_REVIEW.md (Issues 6 and 8 most relevant)
- docs/specs/spec-api.md (Sections 1-3)
- docs/prompts/prompt-api.md (Session A only)

Reminders:
- get_session() must JOIN elections to populate election_name (Issue 8)
- DoneEvent uses model with timestamp — not a raw dict (Issue 6)

Execute Session A. Update STATUS.md when done.
```

**Builds:** `config.py`, `models.py`, `session/store.py` (all 9 store functions), tests.

**Gate:**
```bash
python -m pytest tests/api/test_session_store.py -v
# Must pass: test_get_session_returns_election_name_via_join,
#            test_update_session_status_rejects_invalid_transition,
#            test_processing_to_processing_raises_409
```

---

### Session 4-B — Routers and SSE Streaming

**Milestone ID:** `4B`  
**Depends on:** `4A`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-api.md` (Sections 2, 4), `prompt-api.md` (Session B only)

**Starter prompt:**
```
Read STATUS.md — confirm 4A complete.

Read:
- CLAUDE.md
- docs/specs/spec-api.md (Sections 2 and 4)
- docs/prompts/prompt-api.md (Session B only)

SSE non-negotiables:
- X-Accel-Buffering: no header on every SSE response
- done event fires in finally block — always, even on error paths
- done event uses DoneEvent model (has timestamp)
- 409 SESSION_BUSY if session.status == "processing"

Execute Session B. Update STATUS.md when done.
```

**Builds:** `routers/sessions.py`, `messages.py`, `reports.py`, `main.py`, tests.

**Gate:**
```bash
MOCK_CLAUDE=true MOCK_EXTERNAL_APIS=true python -m pytest tests/api/ -v
# Must pass: test_sse_response_has_x_accel_buffering_header,
#            test_done_event_fires_on_error_path, test_concurrent_message_returns_409

uvicorn apps.api.main:app --port 8001 &
sleep 2 && curl -s http://localhost:8001/health | python -m json.tool && kill %1
```

---

### Session 4-C — Startup, Middleware, Docker

**Milestone ID:** `4C`  
**Depends on:** `4B`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-api.md` (Sections 5–6), `prompt-api.md` (Session C only)

**Starter prompt:**
```
Read STATUS.md — confirm 4B complete.
Read: CLAUDE.md, docs/specs/spec-api.md (Sections 5-6),
      docs/prompts/prompt-api.md (Session C only)
Execute Session C. Run Definition of Done from Section 9 before marking complete.
Update STATUS.md when done.
```

**Builds:** `middleware/logging.py`, startup sequence, `docker-compose.yml`, `.env.example`, tests.

**Gate:**
```bash
MOCK_CLAUDE=true MOCK_EXTERNAL_APIS=true python -m pytest tests/api/ -v --tb=short
docker-compose up -d && sleep 5 && curl -s http://localhost:8000/health && docker-compose down
```

**Phase 4 complete gate:** `MOCK_CLAUDE=true MOCK_EXTERNAL_APIS=true python -m pytest tests/ -v --tb=short` — Zero failures across all backend tests.

---

## Phase 5 — Frontend

**Spec:** `docs/specs/spec-frontend.md`  
**Prompt:** `docs/prompts/prompt-frontend.md`  
**Output:** `apps/web/`  
**Depends on:** Phase 4 gate passed

### Session 5-A — Types, i18n, API Client

**Milestone ID:** `5A`

**Files to open:**
- `STATUS.md` ← confirm Phase 4 complete
- `CLAUDE.md`, `docs/INTEGRATION_REVIEW.md`
- `docs/specs/spec-frontend.md` (Sections 6–7)
- `docs/prompts/prompt-frontend.md` (Session A only)

**Starter prompt:**
```
Read STATUS.md — confirm Phase 4 complete.

Then read:
- CLAUDE.md
- docs/INTEGRATION_REVIEW.md (Issues 1 and 6)
- docs/specs/spec-frontend.md (Sections 6-7)
- docs/prompts/prompt-frontend.md (Session A only)

Reminders:
- ElectionSummary and PrecinctInfo are in the spec — include them in types.ts (Issue 1)
- DoneEvent has a timestamp field (Issue 6)
- SSE uses fetch + ReadableStream, NOT native EventSource (POST endpoint)

Execute Session A. Update STATUS.md when done.
```

**Builds:** `lib/types.ts`, `lib/i18n.ts`, `lib/api.ts`, `locales/en.json`, tests.

**Gate:**
```bash
cd apps/web && npx tsc --noEmit
npx jest __tests__/lib/ --passWithNoTests
# Must pass: test_t_interpolates_variables, test_streamMessage_handles_split_chunks,
#            test_getSession_returns_null_on_404
```

---

### Session 5-B — Hooks

**Milestone ID:** `5B`  
**Depends on:** `5A`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-frontend.md` (Sections 3.2–3.6), `prompt-frontend.md` (Session B only)

**Starter prompt:**
```
Read STATUS.md — confirm 5A complete.

Read:
- CLAUDE.md
- docs/specs/spec-frontend.md (Sections 3.2-3.6)
- docs/prompts/prompt-frontend.md (Session B only)

Critical: all localStorage access must be inside useEffect.
Next.js runs components server-side during build — localStorage does not exist there.
Access outside useEffect causes `npm run build` to fail with "window is not defined".

Execute Session B. Update STATUS.md when done.
```

**Builds:** `hooks/useSession.ts`, `useSSEStream.ts`, `useReport.ts`, tests.

**Gate:**
```bash
cd apps/web && npx tsc --noEmit
npx jest __tests__/hooks/ --passWithNoTests
# Must pass: test_clears_localstorage_and_creates_new_on_404,
#            test_isStreaming_false_after_done, test_streamError_set_on_fetch_failure
```

---

### Session 5-C — Report View Components

**Milestone ID:** `5C`  
**Depends on:** `5B`

**Files to open:** `STATUS.md`, `CLAUDE.md`, `spec-frontend.md` (Sections 4, 9), `prompt-frontend.md` (Session C only)

**Starter prompt:**
```
Read STATUS.md — confirm 5B complete.

Read:
- CLAUDE.md
- docs/specs/spec-frontend.md (Sections 4 and 9)
- docs/prompts/prompt-frontend.md (Session C only)

Neutrality non-negotiables (CLAUDE.md):
- Labels are exactly "For" and "Against" — never "Support"/"Oppose"
- proponent_argument and opponent_argument always rendered as a pair
- Missing candidate positions render "No public statement found on X" — never omitted
- No red/blue color scheme

Execute Session C. Update STATUS.md when done.
```

**Builds:** All report components (SourceList, LimitedDataCard, CandidatePanel, MeasureCard, RaceCard, StalenessBar, ReportHeader, ReportView), report page, print CSS, tests.

**Gate:**
```bash
cd apps/web && npx tsc --noEmit
npx jest __tests__/components/ --passWithNoTests
# Must pass: test_renders_both_for_and_against_sections,
#            test_never_silently_omits_priority_topic,
#            test_renders_limited_data_card_for_limited_completeness,
#            test_renders_nothing_for_fresh, test_renders_items_in_api_order
```

---

### Session 5-D — Chat View, Wiring, Final Build

**Milestone ID:** `5D`  
**Depends on:** `5C`

**Files to open:**
- `STATUS.md` ← confirm 5C complete
- `CLAUDE.md`
- `docs/specs/spec-frontend.md` (Sections 3, 10, 11)
- `docs/prompts/prompt-frontend.md` (Session D only)

**Starter prompt:**
```
Read STATUS.md — confirm 5C complete.

Read:
- CLAUDE.md
- docs/specs/spec-frontend.md (Sections 3, 10, 11)
- docs/prompts/prompt-frontend.md (Session D only)

Execute Session D. After building, run every item in the Definition of Done (Section 11).
Do not mark complete until `npm run build` passes with zero errors.
This is the final milestone — update STATUS.md to mark the project complete.
```

**Builds:** All chat components (ProgressBubble, PriorityChips, MessageBubble, InputBar, MessageThread, ChatView), shared components (Header, DisclaimerBanner), root pages, next.config.js, tests.

**Gate:**
```bash
cd apps/web
npx tsc --noEmit && npx jest --passWithNoTests && npm run build
# All three must pass with zero errors.

# Manual smoke test (required before marking 5D complete):
# 1. cd ../api && uvicorn main:app --port 8000
# 2. npm run dev → open http://localhost:3000
# 3. Welcome message appears, input focused
# 4. Enter zip code — item-by-item progress events appear
# 5. "View Full Ballot Guide" appears — click it — report renders at /report/[id]
# 6. Open report URL in incognito — shared disclaimer banner appears
# 7. Print preview on report — clean layout, source URLs visible as text
# 8. Reload http://localhost:3000 — "Welcome back" message, no new session created
```

**Project complete gate:**
```bash
MOCK_CLAUDE=true MOCK_EXTERNAL_APIS=true python -m pytest tests/ -v --tb=short
cd apps/web && npx tsc --noEmit && npx jest && npm run build
docker-compose up -d && sleep 5 && curl -s http://localhost:8000/health && docker-compose down
```

---

## Appendix A — Environment Variables

Create `.env` at repo root. Never commit it (gitignored). Use `.env.example` as template.
```bash
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_CIVIC_API_KEY=...
NEWSAPI_KEY=...
OPENFEC_API_KEY=...       # Free key: https://api.data.gov/signup/

# Set these for all agent build sessions
MOCK_EXTERNAL_APIS=true
MOCK_CLAUDE=true

DB_PATH=./data/ballot-guide.db
APP_VERSION=0.1.0
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
```

## Appendix B — Files Every Agent Session Needs

1. `STATUS.md` — read first, always
2. `CLAUDE.md` — project rules, always
3. `docs/INTEGRATION_REVIEW.md` — read when starting each new phase
4. The spec and prompt scoped to the current session only — nothing else