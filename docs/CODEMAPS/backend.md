<!-- Generated: 2026-04-20 | Files scanned: 33 | Token estimate: ~950 -->

# Backend Architecture

## API Routes

```
GET  /health                          --> routers/health.py:health_check        --> SQLite probe
GET  /api/v1/elections                --> routers/elections.py:list_elections    --> queries.py
POST /api/v1/session                  --> routers/sessions.py:create_new_session --> store.create_session
GET  /api/v1/session/{id}             --> routers/sessions.py:get_session_metadata --> store.get_session
POST /api/v1/session/{id}/message     --> routers/messages.py:send_message      --> runner.run_orchestrator (SSE)
GET  /api/v1/session/{id}/report      --> routers/reports.py:get_session_report  --> store.get_report
```

## Orchestrator Pipeline

```
runner.py:run_orchestrator()
  |
  +-- Stage 1: stages/intake.py              --> LLM (intake.txt)            --> IntakeResult
  +-- Stage 2: stages/ballot_resolver.py     --> MCP get_ballot_by_address   --> BallotResolverResult
  +-- Stage 3a: stages/measure_analyst.py    --> MCP (4 tools) + LLM         --> MeasureAnalysis[]
  +-- Stage 3b: stages/candidate_analyst.py  --> MCP (3 tools) + LLM         --> RaceAnalysis[]
  +-- Stage 4: stages/relevance_ranker.py    --> LLM (relevance_ranking)     --> RelevanceScore[]
  +-- Stage 5: stages/report_assembler.py    --> Pure sync join              --> BallotReport
  +-- Follow-up: stages/follow_up.py         --> MCP + LLM (follow_up)       --> (answer, sources)
```

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| main.py | 146 | FastAPI app, lifespan, middleware, routers |
| config.py | 79 | Settings singleton (pydantic-settings, fail-fast) |
| models.py | 107 | API request/response models, APIError |
| session/store.py | 266 | Session CRUD, state machine, report persistence |
| db/connection.py | 107 | aiosqlite context mgr, migration runner |
| db/queries.py | 141 | Canonical query functions (never ad-hoc SQL) |
| db/versioning.py | 103 | Data version hashing, freshness detection |
| orchestrator/runner.py | 236 | Stage sequencing, event streaming |
| orchestrator/llm_client.py | 170 | google-genai SDK wrapper, prompt loading, mock mode (MOCK_LLM) |
| orchestrator/schemas.py | 205 | Stage data contracts (11 Pydantic models) |
| orchestrator/events.py | 113 | SSE event types (9 event classes) |
| middleware/logging.py | 63 | Raw ASGI structured JSON request logging |

## Session State Machine

```
active --> processing --> active
                     --> error --> processing
```

Enforced in store.py:_VALID_TRANSITIONS. Never bypass with direct SQL.

## Prompts (apps/api/orchestrator/prompts/)

| File | Lines | Stage |
|------|-------|-------|
| system.txt | 33 | Injected into every LLM call (neutrality rules) |
| intake.txt | 33 | Stage 1: extract zip + priorities |
| measure_analysis.txt | 62 | Stage 3a: analyze ballot measure |
| candidate_analysis.txt | 59 | Stage 3b: analyze candidate |
| relevance_ranking.txt | 40 | Stage 4: score items vs priorities |
| follow_up.txt | 39 | Follow-up Q&A on existing report |

## Error Handling

- All non-200 responses use `APIError(error_code, message, detail)` model
- MCP tool failures return `ToolError` (structured, never raw exceptions)
- LLM schema failures retry up to 3x, then degrade gracefully
- DoneEvent always emitted in finally block (even on error)
