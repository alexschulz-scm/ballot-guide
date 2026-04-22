# CLAUDE.md — Ballot Guide

Read this file at the start of every session. It is the single source of truth for project-wide constraints. Spec files add detail. This file sets the rules that cannot be overridden by any spec.

---

## What This Project Is

An AI-powered ballot guide for Florida voters. Users enter their address and priorities; the system returns a personalized, factual, source-cited summary of everything on their ballot. It never recommends how to vote.

**MVP scope:** Florida only. English only. SQLite. Azure Container Apps.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (TypeScript) |
| Backend API | FastAPI (Python 3.11+) |
| Agent | Claude Sonnet via Anthropic SDK, tool-use loop |
| MCP Servers | Python, `mcp` SDK, stdio transport |
| Database | SQLite with WAL mode, `aiosqlite` for async |
| Containerization | Docker, Docker Compose for local dev |
| Hosting | Azure Container Apps |

---

## Repository Structure

```
ballot-guide/
├── CLAUDE.md                    ← you are here
├── apps/
│   ├── web/                     # Next.js frontend
│   └── api/                     # FastAPI backend + agent orchestrator
├── mcp_servers/                 # Python package (underscore — importable)
│   ├── shared/                  # Shared Pydantic models and cache helpers
│   ├── ballot_data/             # Ballot, candidate, measure, finance data
│   ├── legislation/             # Legal text fetching and parsing
│   └── news/                    # News search and bias ratings
├── data/
│   └── seed/                    # FL 2022 historical election seed data
├── tests/
│   ├── mcp_servers/
│   ├── api/
│   └── web/
├── docs/
│   ├── specs/                   # Component specs (read before building)
│   └── prompts/                 # Build prompts (plan + build phases)
└── infra/                       # Docker, Azure IaC
```

---

## Absolute Rules — Never Violate These

### Data & Architecture
- **MCP servers are the only path to external data.** The agent orchestrator never calls external APIs directly.
- **Cache before every external call.** Check SQLite `api_cache` first. No exceptions.
- **Florida only in MVP.** Reject non-Florida requests at the entry point. Do not call external APIs for non-Florida inputs.
- **SQLite only for MVP.** No PostgreSQL, no Redis, no other databases.

### Code Quality
- **Pydantic models for all tool inputs and outputs.** No raw dicts crossing component boundaries.
- **No LLM calls inside MCP servers.** Reasoning and summarization happen in the agent orchestrator only.
- **No hardcoded credentials.** All secrets via environment variables. Never in code, never in git.
- **No functions longer than 40 lines.** Split into named helpers. This makes agent-generated code reviewable.
- **No silent failures.** Every error is caught, logged, and returned as a structured `ToolError`.

### AI / Neutrality
- **No recommendations.** Output schemas have no recommendation field. Do not add one.
- **Both sides always.** Measure summaries always include proponent AND opponent arguments.
- **Source every claim.** All data returned by MCP servers includes a `sources` list.

### Testing
- **Write tests before marking a task done.** Tests are part of the task, not a follow-up.
- **Tests must run offline.** All external API calls mocked in tests. Use `MOCK_EXTERNAL_APIS=true`.
- **Do not rewrite tests to make them pass.** Fix the code. The test is the source of truth.

---

## Environment Variables

All required. The app will not start without them.

```bash
# Google Gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# Google Civic
GOOGLE_CIVIC_API_KEY=

# NewsAPI
NEWSAPI_KEY=

# OpenFEC (free key: https://api.data.gov/signup/)
OPENFEC_API_KEY=

# Database
DB_PATH=/data/ballot-guide.db

# Development
MOCK_EXTERNAL_APIS=false    # set true in tests to skip real API calls
LOG_LEVEL=INFO
```

---

## Topic Taxonomy

The canonical list of priority topics. Only these values are valid in `topic_tags` and `priorities_json`. Do not add new topics without updating this file.

```
housing, education, taxes, healthcare, environment,
public_safety, economy, voting_rights, infrastructure, senior_services
```

---

## Data Completeness States

Used across all MCP server responses. Values must match exactly.

| Value | Meaning | UI Behavior |
|-------|---------|-------------|
| `full` | All expected fields populated | Normal display |
| `partial` | Some optional fields missing | Display with note |
| `limited` | Only basics available (name, type, status) | "Limited Data" banner + link to official source |

---

## Common Mistakes to Avoid

These have caused problems before. Check against this list when reviewing generated code.

- **Returning dicts instead of Pydantic models** from tool handlers — breaks downstream validation silently
- **Missing `cache_hit` field** on responses — required by orchestrator for telemetry
- **TTL as a magic number** in tool code — TTL values belong in a config constant, not inline
- **Catching all exceptions with bare `except:`** — always catch specific exceptions
- **Not checking `MOCK_EXTERNAL_APIS`** in source clients — tests will make real API calls
- **`topic_tags` containing values not in the taxonomy** — causes relevance ranker to silently ignore them
- **LLM call inside an MCP server** — always wrong, always move to the orchestrator

---

## When You Are Unsure

1. Check the relevant spec in `docs/specs/`
2. Check this file
3. **Stop and ask** — do not guess and implement. Describe the ambiguity and the two most reasonable options.

The cost of building the wrong thing is always higher than the cost of asking a clarifying question.

---

## Definition of Done (Universal)

Every task is done when:
- [ ] Acceptance criteria from the spec pass
- [ ] Tests written and passing
- [ ] No hardcoded secrets or magic numbers
- [ ] No functions over 40 lines
- [ ] All errors return `ToolError` (MCP) or structured HTTP error (API)
- [ ] Runs in Docker Compose without errors
- [ ] No TODOs in code (convert to comments with `# FUTURE:` prefix)

---

## Orchestrator-Specific Rules

*(Added after spec-agent-orchestrator.md was written)*

- **Prompts live in `.txt` files** — `apps/api/orchestrator/prompts/`. Never hardcode prompt strings in Python.
- **Stages never call each other** — only `runner.py` sequences stages. If a stage needs data from another stage, `runner.py` passes it as a parameter.
- **No Claude calls outside `claude_client.py`** — all Anthropic SDK usage is centralized there.
- **Retry on schema failure, degrade gracefully on repeated failure** — never fail the whole report because one item failed.
- **`report_assembler.py` is a pure sync function** — no Claude, no MCP, no async. If you're adding an external call there, it belongs in an earlier stage.
- **Forbidden output fields (any schema, any file):** `recommendation`, `suggested_vote`, `lean`, `preferred_candidate`, `vote_for`
- **Forbidden `relevance_reason` phrases:** "help you", "benefit you", "support your goal", "align with your values", "better for you", "improve your"
- **Temperature is 0.1** — not configurable per call. Do not change this without updating the spec.

---

## API Layer-Specific Rules

*(Added after spec-api.md was written)*

- **Routers are thin** — validate input, delegate to store/orchestrator, format response. No business logic.
- **`X-Accel-Buffering: no` on all SSE responses** — without this, nginx buffers the stream and events don't arrive progressively.
- **`done` event is always the last SSE event** — use a `finally` block. Never conditional.
- **All non-200 responses use `APIError` model** — no raw `HTTPException` with string detail.
- **Session status transitions are enforced in `update_session_status`** — never bypass with a direct SQL update.
- **`aiosqlite` only in async routes** — never use `sqlite3` (synchronous) inside async FastAPI handlers.
- **Migrations run at startup only** — never inside request handlers.
- **WAL mode set on every connection open** — not once at startup but on each `get_db()` context entry.
- **CORS origins from config** — never hardcoded. `http://localhost:3000` ≠ `http://127.0.0.1:3000`.

---

## Cross-Layer Import Rules

*(Added after integration review)*

- **Orchestrator writes session state via `session/store.py`** — the orchestrator calls store functions directly for all session writes. Import path: `from apps.api.session.store import update_session_after_intake` etc. The orchestrator does NOT write to SQLite directly with raw SQL.
- **`session/store.py` has no imports from `orchestrator/`** — this is a one-way dependency. Store → nothing in orchestrator. Orchestrator → store functions only.
- **`SourceCitation` is the single shared source type** — used by MCP servers, orchestrator, and frontend. Never use `DataSource` — that name was retired in the integration review. The canonical definition lives in `mcp-servers/shared/models.py` and is imported by orchestrator schemas.

---

## Frontend-Specific Rules

*(Added after spec-frontend.md was written)*

- **No hardcoded strings in JSX** — all user-facing text via `t()` from `lib/i18n.ts`
- **No `fetch` calls in components or hooks** — only in `lib/api.ts`
- **No SSE parsing in components** — only in `useSSEStream` hook
- **No `localStorage` access outside `useSession`** — and only inside `useEffect` (SSR guard)
- **Do not re-sort report items** — the API returns them in correct relevance order; trust it
- **`proponent_argument` and `opponent_argument` always render as a pair** — never one without the other
- **Labels are "For" and "Against"** — never "Support"/"Oppose", "Yes side"/"No side"
- **Missing candidate positions render explicit text** — never silently omitted
- **No red/blue partisan color scheme** — use the specified civic palette only
- **No recommendation UI** — no star ratings, no outcome highlighting, no "suggested vote"
- **"View Full Ballot Guide" navigates in same tab** — not `target="_blank"`
- **`POST /session` called once per page load** — check localStorage first, never call twice
