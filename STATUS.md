# Ballot Guide — Project Status

**Maintained by:** Claude Code (agent updates this file at the end of every session)  
**Read by:** Claude Code (agent reads this at the start of every session)  
**Owner:** Never edited manually — let the agent maintain it

---

## Current State

**Project complete.** All 15 sessions (1A through 5D) finished. All 54 frontend tests passing, `tsc --noEmit` clean, `npm run build` passes with zero errors.

---

## Milestone Tracker

### Phase 1 — Database
- [x] `1A` — Schema, migrations, SQLite config
- [x] `1B` — Seed data and query functions

### Phase 2 — MCP Servers
- [x] `2A` — ballot-data-mcp: foundation and cache
- [x] `2B` — ballot-data-mcp: remaining tools
- [x] `2C` — legislation-mcp and news-mcp

### Phase 3 — Orchestrator
- [x] `3A` — Schemas, events, Claude client, intake stage
- [x] `3B` — Analysis stages and relevance ranker
- [x] `3C` — Runner, report assembler, end-to-end

### Phase 4 — API Layer
- [x] `4A` — Config, models, session store
- [x] `4B` — Routers and SSE streaming
- [x] `4C` — Startup, middleware, Docker

### Phase 5 — Frontend
- [x] `5A` — Types, i18n, API client
- [x] `5B` — Hooks
- [x] `5C` — Report view components
- [x] `5D` — Chat view, wiring, final build

---

## Session Log

*(Agent appends an entry here at the end of every session)*

### Campaign Finance Migration — 2026-03-03
**Completed:** Replaced OpenSecrets API client with OpenFEC (federal) + FL Division of Elections (state/local) per `docs/specs/spec-mcp-campaign-finance-change.md`
**Files created:**
- `mcp_servers/ballot_data/sources/openfec.py` (OpenFEC API client — federal races, urllib-based, mock mode, `_map_entity_type` for donor categories)
- `mcp_servers/ballot_data/sources/fl_finance.py` (FL DoE CSV client — state/local races, no API key, bulk CSV download + parse)
**Files deleted:**
- `mcp_servers/ballot_data/sources/opensecrets.py`
**Files modified:**
- `mcp_servers/ballot_data/tools/finance.py` (routing logic: `fed-*` → OpenFEC, `fl-*`/`local-*` → FL DoE, unknown → OpenFEC with FL DoE fallback; env var `OPENSECRETS_API_KEY` → `OPENFEC_API_KEY`)
- `apps/api/config.py` (`OPENSECRETS_API_KEY` → `OPENFEC_API_KEY` in Settings class and `validate_required`)
- `.env.example` (replaced OPENSECRETS with OPENFEC + api.data.gov signup link)
- `ROADMAP.md` (Appendix A env var update)
- `CLAUDE.md` (env var section updated)
- `tests/mcp_servers/conftest.py` (env var fixture update)
- `tests/api/conftest.py` (env var default update)
- `tests/api/test_startup.py` (OPENSECRETS → OPENFEC in TestSettings and assertion)
- `tests/mcp_servers/test_ballot_data.py` (Test 11 updated + 3 new acceptance tests)
**Gate result:** All 37 MCP tests passed, all 52 API tests passed (89 total)
**Acceptance criteria verified:**
- AC-MCP-18: `fed-*` entity_id routes to OpenFEC (monkeypatch verified)
- AC-MCP-19: `fl-*` entity_id routes to FL DoE (monkeypatch verified)
- AC-MCP-20: Mock mode returns valid CampaignFinanceSummary with `data_completeness: "full"`
- Zero `OPENSECRETS` references remain in any `.py` source file
**Notes:** Output schemas (CampaignFinanceSummary, DonorSummary, IndustryDonation) are unchanged — no downstream impact. Routing logic lives in the tool handler (`finance.py`), not in individual source clients — each client is a pure fetch-and-parse module. `openfec.py` includes a 3-step lookup: find FEC candidate ID → fetch totals → fetch top donors. `fl_finance.py` uses `csv.DictReader` to parse bulk CSV, filters by `candidate_id` column matching `entity_id`.

### 5D — 2026-03-03
**Completed:** Chat view components, wiring, final build — 7 chat/shared components, page.tsx + layout.tsx + globals.css updates, 13 new tests, Definition of Done verified
**Files created:**
- `apps/web/src/components/chat/ProgressBubble.tsx` (SSE event → status label mapping with animated pulse)
- `apps/web/src/components/chat/PriorityChips.tsx` (10 taxonomy chips, toggle selection, formatted message submit)
- `apps/web/src/components/chat/MessageBubble.tsx` (user right-aligned, assistant left-aligned, plain text with newlines)
- `apps/web/src/components/chat/InputBar.tsx` (text input + send button, Enter key, disabled state)
- `apps/web/src/components/chat/MessageThread.tsx` (message list, progress bubble, view report button, auto-scroll)
- `apps/web/src/components/chat/ChatView.tsx` (orchestrates session + SSE hooks, event-driven chip/report visibility, buildReportSummary)
- `apps/web/src/components/shared/Header.tsx` (wordmark + tagline for chat view)
- `apps/web/src/__tests__/components/chat/PriorityChips.test.tsx` (5 tests)
- `apps/web/src/__tests__/components/chat/ChatView.test.tsx` (5 tests — mocks useSession + useSSEStream with stable refs)
- `apps/web/src/__tests__/components/chat/MessageThread.test.tsx` (3 tests)
**Files modified:**
- `apps/web/src/locales/en.json` (added chat.progress.* keys: starting, found_ballot, analyzing, analyzing_item, ranking, working)
- `apps/web/src/app/page.tsx` (replaced create-next-app boilerplate with `<ChatView />`)
- `apps/web/src/app/layout.tsx` (updated metadata: title + description for Ballot Guide)
- `apps/web/src/app/globals.css` (replaced default palette with civic palette: --background #FAFAF8, --foreground #1A1A18, --accent #1B4FD8; removed dark mode block)
**Gate result:** All 54 frontend tests passed (13 new chat tests + 41 existing), `tsc --noEmit` zero errors, `npm run build` zero errors
**Notes:** This is the final milestone — all 15 sessions complete. ChatView uses stable mock pattern for useSSEStream in tests (single `jest.fn()` with `mockImplementation` rebind per render) to avoid stale mock reference across React re-renders. `buildReportSummary` is a pure template function (not AI-generated) that shows top 3 items by relevance with their relevance reasons. PriorityChips does not submit when zero chips are selected (button is disabled). Civic palette uses off-white (#FAFAF8), near-black (#1A1A18), and civic blue (#1B4FD8) — no red/blue partisan colors. Dark mode block removed (not in spec). All user-facing strings via `t()` from locales/en.json. Task D8 (next.config) skipped — already done in 5A.

### 5C — 2026-03-03
**Completed:** Report view components — 8 React components, Next.js report page route, print CSS, 14 component tests
**Files created:**
- `apps/web/src/components/report/SourceList.tsx` (linked source list with bias ratings)
- `apps/web/src/components/report/LimitedDataCard.tsx` (fallback for limited data items, hardcoded FL/LWV links)
- `apps/web/src/components/report/CandidatePanel.tsx` (candidate positions per priority — never silently omits)
- `apps/web/src/components/report/MeasureCard.tsx` (7-section measure card — For/Against always paired, same weight)
- `apps/web/src/components/report/RaceCard.tsx` (side-by-side desktop, stacked mobile via flex)
- `apps/web/src/components/report/StalenessBar.tsx` (null for fresh, blue for stale, yellow for very_stale)
- `apps/web/src/components/report/ReportHeader.tsx` (election name, priorities, date, shared disclaimer, staleness)
- `apps/web/src/components/report/ReportView.tsx` (orchestrates useReport hook, shared detection, item rendering)
- `apps/web/src/app/report/[sessionId]/page.tsx` (Next.js 16 page with async params)
- `apps/web/src/test-setup.ts` (@testing-library/jest-dom import for custom matchers)
- `apps/web/src/__tests__/components/report/MeasureCard.test.tsx` (5 tests)
- `apps/web/src/__tests__/components/report/RaceCard.test.tsx` (2 tests)
- `apps/web/src/__tests__/components/report/CandidatePanel.test.tsx` (2 tests)
- `apps/web/src/__tests__/components/report/StalenessBar.test.tsx` (3 tests)
- `apps/web/src/__tests__/components/report/ReportView.test.tsx` (2 tests)
**Files modified:**
- `apps/web/src/app/globals.css` (added print CSS: .no-print, .ballot-card, link URL display, 12pt body)
- `apps/web/jest.config.ts` (added setupFilesAfterEnv for @testing-library/jest-dom)
**Gate result:** All 41 frontend tests passed (14 new component tests + 27 existing)
**Notes:** Neutrality rules strictly enforced — For/Against labels are exactly "For" and "Against" (tested), both arguments always rendered as a pair in same-weight containers, missing candidate positions always show "No public statement found on X" (tested). MeasureCard uses helper functions (Header, Outcomes, FiscalImpact, ForAgainst) to stay under 40-line limit while keeping all 7 sections. For section uses green-tinted left border per spec; Against uses neutral gray — avoids red/blue partisan colors. ReportView does NOT re-sort items — renders in API order (tested). Shared session detection compares URL sessionId with localStorage value inside useEffect (SSR-safe). Next.js 16 requires `await params` in server components (params is a Promise). Jest setup: `setupFilesAfterEnv` is the correct config key (not `setupFilesAfterFramework`).

### 5B — 2026-03-03
**Completed:** Three React hooks — useSession, useSSEStream, useReport — fully tested
**Files created:**
- `apps/web/src/hooks/useSession.ts` (localStorage-backed session management with SSR-safe useEffect)
- `apps/web/src/hooks/useSSEStream.ts` (SSE streaming state — events, latestEvent, isStreaming, sendMessage)
- `apps/web/src/hooks/useReport.ts` (report fetching with freshness tracking and refetch)
- `apps/web/src/__tests__/hooks/useSession.test.ts` (4 tests)
- `apps/web/src/__tests__/hooks/useSSEStream.test.ts` (7 tests)
- `apps/web/src/__tests__/hooks/useReport.test.ts` (3 tests)
**Files modified:**
- `apps/web/package.json` (added @testing-library/react, @testing-library/jest-dom, jest-environment-jsdom)
**Gate result:** All 27 frontend tests passed (14 new hook tests + 13 existing)
**Notes:** All localStorage access is inside useEffect (SSR-safe — no "window is not defined" errors during build). Hook tests use `@jest-environment jsdom` docblock to run in jsdom while existing lib tests stay in node environment. `useSSEStream` uses a ref (`streamingRef`) alongside state to prevent double-send race conditions — React state updates are async but ref is synchronous. The existing `streamMessage` in api.ts returns `Promise<void>` (3 params), so the hook uses `.then()` instead of a 4th `onDone` callback shown in the build prompt. `useReport` triggers refetch via a `fetchCount` state variable in the useEffect dependency array. `useSession` exports `SESSION_KEY = "ballot_guide_session_id"` constant for test assertions and future consumers.

### 5A — 2026-03-03
**Completed:** Frontend foundation — Next.js project init, TypeScript types (mirroring Python schemas), i18n with externalized strings, centralized API client with SSE streaming
**Files created:**
- `apps/web/` (Next.js project via create-next-app: TypeScript, Tailwind, App Router, ESLint)
- `apps/web/src/lib/types.ts` (all report, event, session, and API types — 8 SSE event types as discriminated union)
- `apps/web/src/lib/i18n.ts` (t() function with dot-path navigation and {var} interpolation)
- `apps/web/src/lib/api.ts` (createSession, getSession, getReport, streamMessage with fetch+ReadableStream SSE)
- `apps/web/src/locales/en.json` (all UI strings: chat, report, freshness, errors, priority chips with emoji)
- `apps/web/src/__tests__/lib/i18n.test.ts` (5 tests)
- `apps/web/src/__tests__/lib/api.test.ts` (8 tests including split-chunk buffer test)
- `apps/web/jest.config.ts` (ts-jest preset, @/ path alias)
**Files modified:**
- `apps/web/next.config.ts` (added API proxy rewrites to FastAPI backend via API_URL env var)
- `apps/web/package.json` (added test script, jest/ts-jest/@types/jest devDependencies)
**Gate result:** All 13 frontend tests passed; all 170 Python tests still pass (regression clean)
**Notes:** ElectionSummary and PrecinctInfo included in types.ts per Integration Review Issue 1. DoneEvent has timestamp field per Issue 6. All SSE event types include timestamp (inherited from base in Python, explicit on each interface in TS). streamMessage uses fetch+ReadableStream (not EventSource) because the message endpoint is POST. Buffer logic holds incomplete lines across chunk boundaries — verified by split-chunk test that splits JSON payload at the midpoint. API client returns null (not throw) for 404 on getSession and 404/202 on getReport. i18n t() falls back to the key string itself for missing paths. create-next-app created a nested .git — removed immediately (apps/web/ is part of the main repo).

### 4C — 2026-03-03
**Completed:** Logging middleware, startup/e2e tests, Docker config, deprecation fixes, 40-line function limit enforcement, DoD verification
**Files created:**
- `apps/api/middleware/__init__.py`
- `apps/api/middleware/logging.py`
- `tests/api/test_startup.py`
- `tests/api/test_e2e.py`
- `requirements.txt`
- `infra/Dockerfile`
- `infra/docker-compose.yml`
**Files modified:**
- `apps/api/config.py` (migrated `class Config` → `model_config = SettingsConfigDict`)
- `apps/api/main.py` (migrated `@app.on_event("startup")` → lifespan context manager, added logging middleware)
- `apps/api/db/connection.py` (refactored `run_migrations` to meet 40-line limit)
- `apps/api/orchestrator/runner.py` (split 131-line `run_orchestrator` into stage helpers)
- `apps/api/orchestrator/claude_client.py` (extracted `_call_real_api` helper)
- `apps/api/orchestrator/stages/candidate_analyst.py` (extracted `_fetch_candidate_data` helper)
- `apps/api/orchestrator/stages/relevance_ranker.py` (extracted `_scrub_scores` helper)
- `apps/api/routers/messages.py` (extracted `_session_not_found`, `_session_busy`, `_handle_error` helpers)
- `apps/api/routers/reports.py` (extracted `_not_found`, `_processing_response` helpers)
- `tests/api/conftest.py` (added `mock_orchestrator_with_items` fixture with full event sequence)
- `tests/api/test_reports.py` (added AC-11 stale freshness test)
**Gate result:** All 170 tests passed (8 new + 162 existing)
**Notes:** `RequestLoggingMiddleware` uses raw ASGI middleware (not Starlette `BaseHTTPMiddleware`) because BaseHTTPMiddleware has known issues consuming StreamingResponse bodies, which would break SSE streams. Middleware extracts session_id from URL path via regex for structured logging. All 8 functions that exceeded 40 lines (across connection.py, runner.py, claude_client.py, candidate_analyst.py, relevance_ranker.py, messages.py, reports.py) were refactored by extracting named helpers. Runner's `_analyze_ballot_items` uses a tuple yield pattern to pass accumulated measures/races back to the caller after iteration. DoD checklist: all 18 AC pass (AC-07 progressive item_analyzed, AC-09 valid JSON, AC-11 stale freshness, AC-17 startup fails w/o key all now tested), CORS tested (allows configured origin, blocks unconfigured), e2e session lifecycle verified, Docker files ready for `docker compose -f infra/docker-compose.yml build`.

### 4B — 2026-03-03
**Completed:** Orchestrator runner, 4 routers (health, sessions, reports, messages/SSE), FastAPI main app, 30 tests
**Files created:**
- `apps/api/orchestrator/runner.py`
- `apps/api/routers/__init__.py`
- `apps/api/routers/health.py`
- `apps/api/routers/sessions.py`
- `apps/api/routers/reports.py`
- `apps/api/routers/messages.py`
- `apps/api/main.py`
- `tests/api/test_health.py`
- `tests/api/test_sessions.py`
- `tests/api/test_reports.py`
- `tests/api/test_messages.py`
- `tests/orchestrator/test_runner.py`
**Files modified:**
- `apps/api/session/store.py` (added `count_messages()`)
- `tests/api/conftest.py` (added env vars, app fixture, async_client, mock orchestrator fixtures)
**Gate result:** All 162 tests passed (30 new + 132 existing)
**Notes:** `runner.py` (missing from 3C) built as prerequisite — async generator sequencing 5 stages, yields events, writes session state via store functions. Runner does NOT yield DoneEvent and does NOT manage session status — both are the router's responsibility. `event_generator` in messages.py uses `try/except/finally` pattern: normal completion sets status to "active", exception sets "error", and `finally` always yields DoneEvent with timestamp. `_safe_set_status()` helper swallows exceptions to prevent finally-block failures from blocking DoneEvent emission. `X-Accel-Buffering: no` header set on every SSE response. `response_model=None` required on routes returning `StreamingResponse | JSONResponse` union types — FastAPI cannot validate union types containing Response subclasses. Config singleton (`settings = Settings()`) requires env vars at import time — test conftest uses `os.environ.setdefault()` before any app imports. `count_messages()` added to store.py for `SessionMetadataResponse.message_count`. MCP `ElectionSummary`/`PrecinctInfo` converted to orchestrator types via `model_validate(ballot.*.model_dump())` in runner.

### 4A — 2026-03-03
**Completed:** API foundation — config, request/response models, session store (10 functions), custom exceptions, .env.example, 21 tests
**Files created:**
- `apps/api/config.py`
- `apps/api/models.py`
- `apps/api/session/__init__.py`
- `apps/api/session/exceptions.py`
- `apps/api/session/store.py`
- `tests/api/__init__.py`
- `tests/api/conftest.py`
- `tests/api/test_session_store.py`
- `.env.example`
**Gate result:** All 132 tests passed (21 new session store + 111 existing)
**Notes:** `get_session()` implements LEFT JOIN to elections table for `election_name` (Integration Review Issue 8). State machine validated in `update_session_status()` — active→processing, processing→active/error, error→processing are valid; processing→processing raises `InvalidTransitionError`. `save_message()` estimates token count as `len(content) // 4` (~4 chars/token for English) so `load_messages_for_session`'s truncation logic works. `load_messages` and `check_data_freshness` delegate to existing `queries.py` and `versioning.py` respectively — no duplication. `update_session_after_intake` uses `COALESCE(?, display_name)` to preserve session-creation name if intake returns None. Tasks A2 (db connection) and A3 (migration) skipped — already built in Phase 1A. **Gap discovered:** `apps/api/orchestrator/runner.py` was NOT created in 3C despite the milestone description — must be built before 4B (messages router needs `run_orchestrator`).

### 3C — 2026-03-02
**Completed:** All 6 orchestrator stage files + 12 stage tests
**Files created:**
- `apps/api/orchestrator/stages/__init__.py`
- `apps/api/orchestrator/stages/intake.py`
- `apps/api/orchestrator/stages/ballot_resolver.py`
- `apps/api/orchestrator/stages/measure_analyst.py`
- `apps/api/orchestrator/stages/candidate_analyst.py`
- `apps/api/orchestrator/stages/relevance_ranker.py`
- `apps/api/orchestrator/stages/report_assembler.py`
- `tests/orchestrator/test_stages.py`
**Gate result:** All 62 tests passed (12 new stage tests + 50 existing)
**Notes:** Stages call MCP handlers via direct Python imports (not subprocess) — simpler and testable via monkeypatch. `ballot_resolver` returns `BallotResolverResult | ErrorEvent`: the dataclass carries both the event and raw ballot data so the runner has everything for Stage 3. `candidate_analyst` accepts `RaceSummary` (not separate race_id/title/type params) to cleanly build `RaceAnalysis`. `report_assembler` is a pure sync function — verified by `inspect.iscoroutine`. All stage tests monkeypatch `call_claude` and MCP handler functions directly (no MOCK_CLAUDE env var needed). Prompt files contain `{...}` JSON examples that break `.format()` — fixed by using explicit `.replace()` for each variable. Event types (`Literal[...]`) must be passed explicitly to Pydantic constructors — there are no defaults.

### 3B — 2026-03-02
**Completed:** Claude client wrapper, 5 prompt files, mock fixture, 8 tests
**Files created:**
- `apps/api/orchestrator/claude_client.py`
- `apps/api/orchestrator/prompts/system.txt`
- `apps/api/orchestrator/prompts/intake.txt`
- `apps/api/orchestrator/prompts/measure_analysis.txt`
- `apps/api/orchestrator/prompts/candidate_analysis.txt`
- `apps/api/orchestrator/prompts/relevance_ranking.txt`
- `tests/fixtures/claude/mock_response.json`
- `tests/orchestrator/test_claude_client.py`
**Gate result:** All 50 tests passed (8 new claude_client + 42 existing)
**Notes:** `call_claude` uses deferred `import anthropic` after the mock check — so `MOCK_CLAUDE=true` tests work without the SDK installed. Temperature is hardcoded at 0.1 inside `call_claude` and not exposed as a parameter per CLAUDE.md. `parse_json_response` strips markdown code fences before JSON parsing. `SchemaValidationError` wraps Pydantic `ValidationError`; `ClaudeError` wraps Anthropic SDK exceptions — callers never see raw library exceptions. `relevance_ranking.txt` OUTPUT FORMAT explicitly states "Start your response with [ and end with ]" because it returns a JSON array, not object. `system.txt` has no OUTPUT FORMAT section (it is a system prompt, not a user-turn prompt). Installed `anthropic==0.84.0`.

### 3A — 2026-03-02
**Completed:** Orchestrator data contracts — all Pydantic output schemas, all event models, 8 tests
**Files created:**
- `apps/api/orchestrator/__init__.py`
- `apps/api/orchestrator/schemas.py`
- `apps/api/orchestrator/events.py`
- `tests/orchestrator/__init__.py`
- `tests/orchestrator/test_schemas.py`
**Gate result:** All 42 tests passed (8 new orchestrator + 34 existing)
**Notes:** `schemas.py` applies 3 integration review fixes: ElectionSummary + PrecinctInfo defined here (Issue 1), SourceCitation used exclusively — no DataSource (Issue 2), DoneEvent timestamp inherited from OrchestratorEvent base (Issue 6 confirmed correct). `IntakeResult.priorities` validator silently drops non-taxonomy values and truncates to max 5 — no ValidationError raised. `MeasureAnalysis.sources` validator raises ValidationError if empty. All event subclasses use `Literal[...]` for `event_type`. `BallotReport` verified to contain none of the 5 forbidden neutrality fields. `CandidateAnalysis.positions` is `dict[str, str]` (Issues 3/4: intentional flattening from MCP CandidatePosition objects done by candidate_analyst stage in 3B).

### 2C — 2026-03-02
**Completed:** legislation-mcp and news-mcp — 2 MCP servers, 4 tool handlers, 2 server entry points, 2 parsers, 15 tests
**Files created:**
- `mcp_servers/legislation/__init__.py`
- `mcp_servers/legislation/constants.py`
- `mcp_servers/legislation/server.py`
- `mcp_servers/legislation/parsers/__init__.py`
- `mcp_servers/legislation/parsers/html_parser.py`
- `mcp_servers/legislation/parsers/pdf_parser.py`
- `mcp_servers/legislation/tools/__init__.py`
- `mcp_servers/legislation/tools/measure_text.py`
- `mcp_servers/legislation/tools/parse_text.py`
- `mcp_servers/news/__init__.py`
- `mcp_servers/news/constants.py`
- `mcp_servers/news/server.py`
- `mcp_servers/news/bias_ratings.json`
- `mcp_servers/news/sources/__init__.py`
- `mcp_servers/news/sources/newsapi.py`
- `mcp_servers/news/tools/__init__.py`
- `mcp_servers/news/tools/bias.py`
- `mcp_servers/news/tools/search.py`
- `tests/mcp_servers/test_legislation.py`
- `tests/mcp_servers/test_news.py`
**Gate result:** All 34 tests passed (8 legislation + 7 news + 19 existing)
**Notes:** `handle_parse_measure_text` is a pure deterministic function — no LLM, no db_path, no cache, no external calls. `handle_get_source_bias` never returns ToolError; unknown domains return `found=False`. Lambda wrappers in `_TOOL_HANDLERS` dicts normalize handlers that take different signatures (some have db_path, some don't). `pdf_parser.py` handles both `ImportError` (pdfplumber not installed) and any parse exception gracefully — always returns `""`. Bias ratings loaded from `bias_ratings.json` are cached in a module-level `_RATINGS_CACHE` to avoid repeated file reads. `search_news` cache key normalizes query to lowercase so "Florida" and "florida" produce the same cache key.

### 2B — 2026-03-02
**Completed:** ballot-data-mcp server — 4 source clients, 4 tool handlers, MCP entry point, test fixtures, 13 tests
**Files created:**
- `mcp_servers/ballot_data/__init__.py`
- `mcp_servers/ballot_data/constants.py`
- `mcp_servers/ballot_data/server.py`
- `mcp_servers/ballot_data/sources/__init__.py`
- `mcp_servers/ballot_data/sources/civic.py`
- `mcp_servers/ballot_data/sources/ballotpedia.py`
- `mcp_servers/ballot_data/sources/fl_elections.py`
- `mcp_servers/ballot_data/sources/opensecrets.py`
- `mcp_servers/ballot_data/tools/__init__.py`
- `mcp_servers/ballot_data/tools/ballot.py`
- `mcp_servers/ballot_data/tools/measure.py`
- `mcp_servers/ballot_data/tools/candidate.py`
- `mcp_servers/ballot_data/tools/finance.py`
- `tests/mcp_servers/conftest.py`
- `tests/mcp_servers/test_ballot_data.py`
**Gate result:** All 19 tests passed (13 new + 6 from 2A)
**Notes:** Source clients all gate on `MOCK_EXTERNAL_APIS=true` for test isolation — no real HTTP calls in tests. `positions_json` in seed data is a flat `{"topic": "text"}` dict; `_build_positions()` in candidate.py wraps each string into a typed `CandidatePosition`. Finance handler checks SQLite `funding_summary_json` first (covers seed candidates without OpenSecrets IDs), then falls back to OpenSecrets API. `conftest.py` inserts `FL-2026-GEN` (is_historical=0) so `_resolve_upcoming_election` has a future election to find. All tool handlers are synchronous (consistent with cache.py using stdlib sqlite3); server.py calls them from async `call_tool` context without await — valid in Python.

### 2A — 2026-03-02
**Completed:** MCP shared layer — all Pydantic models, cache helpers, and tests
**Files created:**
- `mcp_servers/__init__.py`
- `mcp_servers/shared/__init__.py`
- `mcp_servers/shared/models.py`
- `mcp_servers/shared/cache.py`
- `mcp-servers/shared/__init__.py` (filesystem placeholder matching CLAUDE.md structure)
- `mcp-servers/shared/models.py` (filesystem placeholder — Python imports use mcp_servers/)
- `mcp-servers/shared/cache.py` (filesystem placeholder — Python imports use mcp_servers/)
- `tests/mcp_servers/__init__.py`
- `tests/mcp_servers/test_shared_models.py`
**Gate result:** All 6 new tests passed; full suite 55/55 passed
**Notes:** The CLAUDE.md documents the path as `mcp-servers/` (hyphen) but Python cannot import from a hyphenated directory name. The importable Python package lives at `mcp_servers/` (underscore) at the repo root — same pattern as `apps/`. Files were also written to `mcp-servers/` to match the documented filesystem structure, but all imports use `mcp_servers/`. `SourceCitation` is the canonical model name; build prompt Task A1 listed `DataSource` (outdated, pre-integration review) — resolved in favour of CLAUDE.md cross-layer rules. `DataCompleteness` uses `(str, Enum)` for correct JSON serialisation.

### 1B — 2026-03-02
**Completed:** Seed data (3 JSON files + README), seed script, canonical query functions, data versioning
**Files created:**
- `data/seed/README.md`
- `data/seed/fl_2022_election.json`
- `data/seed/fl_2022_measures.json`
- `data/seed/fl_2022_candidates.json`
- `scripts/seed_historical.py`
- `apps/api/db/queries.py`
- `apps/api/db/versioning.py`
- `.gitignore`
- `tests/db/test_seed.py`
- `tests/db/test_queries.py`
- `tests/db/test_versioning.py`
**Gate result:** All 49 tests passed (38 new + 11 from 1A)
**Notes:** `seed_database()` calls `run_migrations()` before inserting so the script works on a fresh DB without a separate migration step. `seed_historical.py` adds repo root to `sys.path` so it can be run directly as a script. Tests use `tmp_path` fixture via conftest for proper isolation.

### 1A — 2026-03-02
**Completed:** Schema, migrations, SQLite config, and migration runner
**Files created:**
- `apps/api/db/migrations/001_initial.sql`
- `apps/api/db/migrations/002_seed_fl_2022.sql`
- `apps/api/db/connection.py`
- `apps/api/db/exceptions.py`
- `apps/api/db/__init__.py`
- `apps/__init__.py`
- `apps/api/__init__.py`
- `tests/__init__.py`
- `tests/db/__init__.py`
- `tests/db/conftest.py`
- `tests/db/test_migrations.py`
- `pytest.ini`
**Gate result:** All 11 tests passed
**Notes:** In-memory SQLite (`:memory:`) cannot be shared across separate aiosqlite connections and does not support WAL mode. Tests use `tempfile.mkstemp` for isolated file-based DBs. The conftest `db` fixture uses the same pattern and should be updated in 1B to use `tmp_path`. `executescript()` was replaced with statement-by-statement execution to preserve transaction atomicity for rollback.

---

## Known Issues / Blockers

*(Agent records any blockers or deferred decisions here)*

- ~~**runner.py missing:** Resolved in 4B.~~
- ~~**Pydantic deprecation warning:** Resolved in 4C — migrated to `model_config = SettingsConfigDict(...)`.~~
- ~~**FastAPI deprecation warning:** Resolved in 4C — migrated to `lifespan` context manager.~~

---

## Agent Instructions

At the **start** of every session:
1. Read this file in full
2. Confirm the prerequisite milestone is checked before starting your session
3. If the prerequisite is not checked, stop and tell the developer

At the **end** of every session:
1. Check the completed milestone box above
2. Update "Current State" section to reflect the new next session
3. Append a session log entry in this format:
```
### [Milestone ID] — [Date]
**Completed:** [what was built]
**Files created:**
- path/to/file1.py
- path/to/file2.py
**Gate result:** All N tests passed
**Notes:** [anything worth flagging for the next session]
```