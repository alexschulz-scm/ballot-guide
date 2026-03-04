# Spec: API Layer

**Status:** Draft v1.0  
**Component:** `apps/api/`  
**Depends on:** `spec-mcp-servers.md`, `spec-agent-orchestrator.md`, `user-flows.md`  
**Consumed by:** `spec-frontend.md`, `spec-database.md`  
**Last updated:** 2026-02-28

---

## 1. Overview

The API layer is the HTTP interface between the Next.js frontend and the agent orchestrator. It is a **thin routing layer** — it does not contain business logic, does not call external APIs, and does not make decisions about ballot content. Its responsibilities are:

- Create and manage anonymous sessions
- Accept user messages, invoke the orchestrator, stream events back as SSE
- Serve cached reports for returning sessions
- Persist session state and message history to SQLite
- Handle request validation and structured error responses

Built with **FastAPI (Python 3.11+)** and **aiosqlite** for async SQLite access.

### What the API is NOT responsible for
- Calling MCP tools directly (orchestrator does this)
- Generating ballot summaries (orchestrator does this)
- Rendering UI (frontend does this)
- Managing external API keys other than passing environment variables to orchestrator
- Rate limiting at MVP (Azure Container Apps handles basic throttling)

---

## 2. Endpoints

Five endpoints for MVP. All return JSON except the SSE stream endpoint.

### Overview

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/session` | Create a new anonymous session |
| `POST` | `/session/{id}/message` | Send message, stream orchestrator events as SSE |
| `GET` | `/session/{id}/report` | Get completed ballot report (cached) |
| `GET` | `/session/{id}` | Get session metadata and status |
| `GET` | `/health` | Liveness check |

Base path: `/api/v1` for all endpoints except `/health`.

---

### 2.1 `POST /api/v1/session`

Creates a new anonymous session. Called on first page load before any message is sent.

**Request body:**
```json
{
  "display_name": "Maria",        // optional
  "language": "en"                // optional, defaults to "en"
}
```

**Response `201 Created`:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-01T10:00:00Z",
  "display_name": "Maria",
  "language": "en",
  "status": "active"
}
```

**Response errors:**
| Status | Code | Condition |
|--------|------|-----------|
| `422` | `INVALID_LANGUAGE` | Language not in supported list (`["en"]` for MVP) |
| `500` | `DB_ERROR` | SQLite write failed |

**Behavior:**
- Generates a UUID v4 `session_id`
- Writes new row to `sessions` table
- Detects browser language from `Accept-Language` header, stores in `sessions.detected_language` (logged for v2, not acted on in MVP)
- `display_name` stored as-is, max 50 characters, no validation beyond length

---

### 2.2 `POST /api/v1/session/{session_id}/message`

Accepts a user message, runs the orchestrator, and streams events back as **Server-Sent Events (SSE)**. This is the primary endpoint — most of the system's work happens here.

**Path parameter:** `session_id` — must be a valid existing session UUID

**Request body:**
```json
{
  "content": "I live in 33101 and care about housing and schools"
}
```

**Response: `200 OK` with `Content-Type: text/event-stream`**

The response body is a stream of SSE events. Each event has this format:
```
event: {event_type}
data: {json_payload}

```
(blank line terminates each event)

**SSE event sequence for a full run:**
```
event: intake_complete
data: {"event_type":"intake_complete","session_id":"...","timestamp":"...","zip_code":"33101","priorities":["housing","education"],"display_name":"Maria"}

event: ballot_found
data: {"event_type":"ballot_found","session_id":"...","timestamp":"...","election_name":"2026 Florida General Election","item_count":10,"message":"Found your ballot — 10 items. Analyzing..."}

event: item_analyzed
data: {"event_type":"item_analyzed","session_id":"...","timestamp":"...","item_id":"FL-2026-A1","item_title":"Amendment 1","items_complete":1,"items_total":10}

[... more item_analyzed events ...]

event: ranking_complete
data: {"event_type":"ranking_complete","session_id":"...","timestamp":"...","top_item_title":"Amendment 3"}

event: report_complete
data: {"event_type":"report_complete","session_id":"...","timestamp":"...","report":{...full BallotReport...}}

event: done
data: {"event_type":"done","session_id":"...","timestamp":"..."}
```

**SSE error event (mid-stream failure):**
```
event: error
data: {"event_type":"error","session_id":"...","timestamp":"...","error_code":"BALLOT_NOT_FOUND","message":"We couldn't find a ballot for zip code 99999. Please check your address.","recoverable":false}

event: done
data: {"event_type":"done","session_id":"...","timestamp":"..."}
```

The `done` event is always the last event, even after an error. The frontend uses it to know the stream has ended.

**Request validation errors (before stream starts):**
| Status | Code | Condition |
|--------|------|-----------|
| `404` | `SESSION_NOT_FOUND` | `session_id` not in database |
| `409` | `SESSION_BUSY` | Orchestrator already running for this session |
| `422` | `EMPTY_MESSAGE` | `content` is empty or whitespace only |
| `422` | `MESSAGE_TOO_LONG` | `content` exceeds 500 characters |

**Behavior:**
- Validates session exists before starting stream
- Sets session status to `"processing"` while orchestrator runs
- Saves each user message to `messages` table before starting orchestrator
- Saves each assistant response to `messages` table after orchestrator completes
- Sets session status back to `"active"` when done (or `"error"` on fatal failure)
- On client disconnect mid-stream: orchestrator continues running, result saved — client can call `GET /session/{id}/report` when it reconnects

**Concurrency guard:**
If a second request comes in for a session that is already `"processing"`, return `409 SESSION_BUSY` immediately. Do not start a second orchestrator run.

---

### 2.3 `GET /api/v1/session/{session_id}/report`

Returns the most recently completed ballot report for a session. Used by:
- The frontend report view (`/report/[id]`)
- Returning users (election day fast-path)
- Shared report links

**Path parameter:** `session_id`

**Response `200 OK`:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "report": { ...BallotReport... },
  "generated_at": "2026-03-01T10:05:00Z",
  "data_freshness": "fresh",
  "display_name": "Maria",
  "priorities": ["housing", "education"]
}
```

**`data_freshness` values:**
| Value | Meaning | Frontend behavior |
|-------|---------|------------------|
| `"fresh"` | Report generated < 24 hours ago, ballot data unchanged | Show normally |
| `"stale"` | Ballot data changed since report was generated | Show staleness banner |
| `"very_stale"` | Report > 7 days old | Show prominent refresh prompt |

**Staleness detection:**
Compare `sessions.data_version` (hash stored when report was generated) against current ballot data version. If different → `"stale"`. If report older than 7 days → `"very_stale"` regardless of data changes.

**Response errors:**
| Status | Code | Condition |
|--------|------|-----------|
| `404` | `SESSION_NOT_FOUND` | Session doesn't exist |
| `404` | `REPORT_NOT_READY` | Session exists but no report yet (orchestrator not run) |
| `202` | `PROCESSING` | Orchestrator currently running — report not ready yet |

**Note on `202`:** When the orchestrator is running, return `202 Accepted` with body `{"status": "processing", "message": "Your ballot guide is being prepared. Connect to the event stream to follow progress."}`. This handles the case where a client loads the report URL while the stream is still running.

---

### 2.4 `GET /api/v1/session/{session_id}`

Returns session metadata. Used by the frontend to restore state on page refresh or return visit.

**Response `200 OK`:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-01T10:00:00Z",
  "updated_at": "2026-03-01T10:05:00Z",
  "display_name": "Maria",
  "language": "en",
  "status": "active",
  "zip_code": "33101",
  "priorities": ["housing", "education"],
  "has_report": true,
  "election_name": "2026 Florida General Election",
  "message_count": 4
}
```

**Response errors:**
| Status | Code | Condition |
|--------|------|-----------|
| `404` | `SESSION_NOT_FOUND` | Session doesn't exist |

**Behavior:** Never returns the full report — only metadata. Full report is served by `GET /report`. This keeps the session restore payload small (<1KB).

---

### 2.5 `GET /health`

Liveness check. Used by Azure Container Apps health probe.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "db": "ok",
  "version": "1.0.0",
  "timestamp": "2026-03-01T10:00:00Z"
}
```

**Response `503 Service Unavailable`:**
```json
{
  "status": "degraded",
  "db": "error",
  "error": "SQLite connection failed",
  "timestamp": "2026-03-01T10:00:00Z"
}
```

**Behavior:** Performs a lightweight SQLite read (`SELECT 1`) to confirm DB is accessible. Returns `503` if it fails. No Claude or MCP health check — those are checked lazily on first use.

---

## 3. SSE Streaming Protocol

### 3.1 Why SSE over WebSockets

SSE is one-directional (server → client) which is exactly the pattern here: the user sends one message, the server streams back a sequence of events. WebSockets add bidirectional complexity for no benefit. SSE also reconnects automatically on disconnect and works over standard HTTP — no upgrade handshake, no connection management on the client.

### 3.2 SSE Format

Each event strictly follows the SSE specification:
```
event: {event_type}\n
data: {json_string}\n
\n
```

Rules:
- `event_type` matches the `event_type` field inside the JSON payload
- JSON payload is always a single line (no pretty-printing)
- Blank line after each event is mandatory — it's how the client knows the event is complete
- The `done` event is always sent last, even after errors
- No heartbeat events for MVP (add if clients report timeout issues)

### 3.3 Client Reconnection

If the client disconnects and reconnects, it calls `GET /session/{id}/report`:
- If report is ready → serve it directly, no need to re-stream
- If report is not ready and orchestrator is still running → return `202 Processing`
- If orchestrator stopped due to error → return the error in the session metadata

The orchestrator always runs to completion regardless of client connection state. Results are always persisted. Clients never lose work by disconnecting.

### 3.4 FastAPI SSE Implementation

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

async def event_generator(session_id: str, message: str, db_path: str):
    async for event in run_orchestrator(session_id, message, db_path):
        yield f"event: {event.event_type}\n"
        yield f"data: {event.model_dump_json()}\n"
        yield "\n"
    # Always send done — use DoneEvent model so timestamp is included
    done = DoneEvent(event_type="done", session_id=session_id, timestamp=datetime.utcnow().isoformat())
    yield f"event: done\n"
    yield f"data: {done.model_dump_json()}\n"
    yield "\n"

@router.post("/session/{session_id}/message")
async def send_message(session_id: str, body: MessageRequest):
    return StreamingResponse(
        event_generator(session_id, body.content, DB_PATH),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"   # disables nginx buffering — critical for SSE
        }
    )
```

The `X-Accel-Buffering: no` header is critical — without it, nginx (used by Azure Container Apps) buffers the response and the client doesn't see events until the buffer fills.

---

## 4. Request / Response Models

All models are Pydantic. Defined in `apps/api/models.py`.

```python
# Request models
class CreateSessionRequest(BaseModel):
    display_name: str | None = None
    language: str = "en"

    @field_validator("display_name")
    def truncate_display_name(cls, v):
        return v[:50] if v else None

    @field_validator("language")
    def validate_language(cls, v):
        if v not in ["en"]:   # expand for v2
            raise ValueError("Unsupported language")
        return v

class SendMessageRequest(BaseModel):
    content: str

    @field_validator("content")
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > 500:
            raise ValueError("Message too long (max 500 characters)")
        return v

# Response models
class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: str
    display_name: str | None
    language: str
    status: str

class SessionMetadataResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    display_name: str | None
    language: str
    status: str
    zip_code: str | None
    priorities: list[str]
    has_report: bool
    election_name: str | None
    message_count: int

class ReportResponse(BaseModel):
    session_id: str
    report: dict              # BallotReport serialized — avoid re-importing orchestrator schemas
    generated_at: str
    data_freshness: str
    display_name: str | None
    priorities: list[str]

class HealthResponse(BaseModel):
    status: str
    db: str
    version: str
    timestamp: str

# Error model — used for all non-200 responses
class APIError(BaseModel):
    error_code: str           # SCREAMING_SNAKE_CASE
    message: str              # user-facing message
    detail: str | None = None # additional technical detail (dev/debug only)
```

---

## 5. Session State Machine

Sessions transition through these states. The API enforces valid transitions.

```
         POST /session
              │
              ▼
           "active"  ──────────────────────────────────────┐
              │                                             │
              │ POST /message received                      │
              ▼                                             │
         "processing" ──► orchestrator runs ──► report saved
              │                                             │
              │ orchestrator complete                       │
              ▼                                             │
           "active" ◄──────────────────────────────────────┘
              │
              │ orchestrator fatal error
              ▼
            "error"
```

Valid transitions:
- `active` → `processing` (on message received)
- `processing` → `active` (on orchestrator complete)
- `processing` → `error` (on fatal orchestrator failure)
- `error` → `processing` (user can retry — send a new message)

Invalid transition (rejected with `409`):
- `processing` → `processing` (no concurrent runs)

---

## 6. Database Operations

The API layer is the only component that reads and writes session state. Operations use `aiosqlite` for async access.

### Session operations (in `apps/api/session/store.py`)

```python
async def create_session(
    display_name: str | None,
    language: str,
    detected_language: str | None,
    db_path: str
) -> str:
    """Creates session, returns session_id (UUID)."""

async def get_session(session_id: str, db_path: str) -> dict | None:
    """Returns session row as dict, or None if not found.
    Joins elections table to populate election_name:
      SELECT s.*, e.name as election_name
      FROM sessions s
      LEFT JOIN elections e ON s.ballot_id = e.id
      WHERE s.id = ?
    election_name is null if ballot_id not yet set (before Stage 2 completes).
    """

async def update_session_status(
    session_id: str,
    status: str,
    db_path: str
) -> None:
    """Updates sessions.status. Validates transition is legal."""

async def update_session_after_intake(
    session_id: str,
    zip_code: str,
    priorities: list[str],
    priorities_raw: str,
    display_name: str | None,
    db_path: str
) -> None:
    """Called by orchestrator after Stage 1 completes."""

async def update_session_after_ballot(
    session_id: str,
    ballot_id: str,
    db_path: str
) -> None:
    """Called by orchestrator after Stage 2 completes."""

async def save_report(
    session_id: str,
    report_json: str,
    data_version: str,
    db_path: str
) -> None:
    """Saves completed report. Called after Stage 5."""

async def get_report(session_id: str, db_path: str) -> dict | None:
    """Returns report_json parsed as dict, or None."""

async def save_message(
    session_id: str,
    role: str,
    content: str,
    db_path: str
) -> None:
    """Saves one message. role must be 'user' or 'assistant'."""

async def load_messages(
    session_id: str,
    db_path: str,
    max_tokens: int = 20000
) -> list[dict]:
    """
    Returns message history as list of {role, content} dicts.
    Truncates oldest messages if total tokens exceeds max_tokens.
    Never drops the first message (contains address + priorities).
    """

async def check_data_freshness(
    session_id: str,
    db_path: str
) -> str:
    """
    Returns "fresh", "stale", or "very_stale".
    Compares sessions.data_version against current ballot data hash.
    """
```

---

## 7. File Structure

```
apps/api/
├── main.py                    # FastAPI app init, router registration, startup
├── config.py                  # Settings from env vars (pydantic-settings)
├── models.py                  # Request/response Pydantic models
├── routers/
│   ├── __init__.py
│   ├── sessions.py            # POST /session, GET /session/{id}
│   ├── messages.py            # POST /session/{id}/message (SSE)
│   └── reports.py             # GET /session/{id}/report
├── session/
│   ├── __init__.py
│   └── store.py               # All SQLite session operations
├── db/
│   ├── __init__.py
│   ├── connection.py          # aiosqlite connection factory, WAL mode setup
│   └── migrations/
│       ├── 001_initial.sql    # Full schema from architecture.md
│       └── migrate.py         # Runs migrations on startup
├── middleware/
│   ├── __init__.py
│   └── logging.py             # Structured request logging
└── orchestrator/              # (from spec-agent-orchestrator.md)
    └── ...
```

---

## 8. Application Startup

`main.py` startup sequence (order matters):

```python
@app.on_event("startup")
async def startup():
    # 1. Validate all required env vars are present — fail fast if missing
    config.validate()
    
    # 2. Ensure /data directory exists (Azure File Share mount point)
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    
    # 3. Run database migrations
    await run_migrations(config.DB_PATH)
    
    # 4. Enable WAL mode on SQLite
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
    
    # 5. Log startup complete with version + config summary (no secrets)
    logger.info(f"Ballot Guide API started. DB: {config.DB_PATH}")
```

If any step fails, the application fails to start. This is intentional — a partially initialized app is worse than no app.

---

## 9. Configuration

All configuration via environment variables. Managed with `pydantic-settings`.

```python
class Settings(BaseSettings):
    # Database
    DB_PATH: str = "/data/ballot-guide.db"
    
    # API
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    
    # Anthropic (passed to orchestrator)
    ANTHROPIC_API_KEY: str    # required, no default
    
    # External APIs (passed to MCP servers)
    GOOGLE_CIVIC_API_KEY: str  # required
    NEWSAPI_KEY: str           # required
    OPENSECRETS_API_KEY: str   # required
    
    # Development
    MOCK_EXTERNAL_APIS: bool = False
    MOCK_CLAUDE: bool = False
    
    def validate(self):
        """Called at startup. Raises if required vars missing."""
        required = [
            self.ANTHROPIC_API_KEY,
            self.GOOGLE_CIVIC_API_KEY,
            self.NEWSAPI_KEY,
        ]
        # Pydantic already validates presence — this is for explicit startup logging
```

---

## 10. CORS Configuration

For MVP, CORS is permissive for local development and locked to the production domain in prod.

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # ["http://localhost:3000"] locally
    allow_credentials=False,               # no cookies, no auth headers
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

---

## 11. Acceptance Criteria

### Session management
- [ ] **AC-API-01:** `POST /session` returns a valid UUID in `session_id` and writes to SQLite
- [ ] **AC-API-02:** `POST /session` with no body creates a session with `display_name: null` and `language: "en"`
- [ ] **AC-API-03:** `GET /session/{id}` for a non-existent ID returns `404` with `error_code: "SESSION_NOT_FOUND"`
- [ ] **AC-API-04:** `POST /session/{id}/message` while session is `"processing"` returns `409` with `error_code: "SESSION_BUSY"`

### SSE streaming
- [ ] **AC-API-05:** SSE response has `Content-Type: text/event-stream` and `X-Accel-Buffering: no` headers
- [ ] **AC-API-06:** Every SSE run ends with a `done` event — including runs that errored mid-stream
- [ ] **AC-API-07:** `item_analyzed` events are emitted progressively — the client receives them before `report_complete`
- [ ] **AC-API-08:** If client disconnects mid-stream, orchestrator continues and report is saved to SQLite
- [ ] **AC-API-09:** SSE events are valid JSON parseable by `JSON.parse()` in the browser

### Report endpoint
- [ ] **AC-API-10:** `GET /session/{id}/report` returns `404` with `error_code: "REPORT_NOT_READY"` when no report exists yet
- [ ] **AC-API-11:** `GET /session/{id}/report` returns `data_freshness: "stale"` when ballot data has changed since report generation
- [ ] **AC-API-12:** `GET /session/{id}/report` returns `202` with status `"processing"` when orchestrator is running

### Input validation
- [ ] **AC-API-13:** `POST /session/{id}/message` with empty `content` returns `422`
- [ ] **AC-API-14:** `POST /session/{id}/message` with `content` > 500 chars returns `422`
- [ ] **AC-API-15:** `POST /session` with `language: "es"` returns `422` with `error_code: "INVALID_LANGUAGE"` (MVP: English only)

### Health and startup
- [ ] **AC-API-16:** `GET /health` returns `200` with `db: "ok"` when SQLite is accessible
- [ ] **AC-API-17:** Application fails to start if `ANTHROPIC_API_KEY` env var is missing
- [ ] **AC-API-18:** On startup, WAL mode is enabled — confirmed by `PRAGMA journal_mode` returning `"wal"`

---

## 12. Definition of Done

- [ ] All 18 acceptance criteria pass
- [ ] Unit tests for every router function and session store function
- [ ] SSE stream tested end-to-end with a mock orchestrator
- [ ] Session state machine tested: all valid transitions pass, invalid `processing→processing` returns `409`
- [ ] Database migration runs cleanly on empty database
- [ ] WAL mode confirmed in startup test
- [ ] All env vars documented in `.env.example` file
- [ ] CORS tested: request from `localhost:3000` succeeds, request from `evil.com` fails
- [ ] `X-Accel-Buffering: no` header present on SSE response
- [ ] All error responses use `APIError` model — no raw FastAPI `HTTPException` with string detail
- [ ] App starts cleanly with `docker compose up`
- [ ] No functions longer than 40 lines

---

## 13. Test Strategy

### Test file locations
```
tests/
└── api/
    ├── conftest.py              # TestClient, mock orchestrator, test DB
    ├── test_sessions.py         # POST /session, GET /session/{id}
    ├── test_messages.py         # POST /session/{id}/message + SSE
    ├── test_reports.py          # GET /session/{id}/report + freshness
    ├── test_session_store.py    # SQLite session operations
    ├── test_startup.py          # Startup sequence, migrations, WAL mode
    └── test_health.py           # GET /health
```

### Test categories

**Router tests (FastAPI TestClient):**
Standard request/response testing. Mock the orchestrator entirely — these tests verify HTTP contracts, not orchestrator behavior.

**SSE stream tests:**
Use `httpx` with `AsyncClient` to consume the SSE stream in tests. Assert events arrive in the correct order and the `done` event always terminates the stream.

```python
async def test_sse_emits_done_event():
    async with AsyncClient(app=app, base_url="http://test") as client:
        events = []
        async with client.stream("POST", f"/api/v1/session/{sid}/message",
                                  json={"content": "33101"}) as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))
        
        assert events[-1]["event_type"] == "done"
```

**Session store tests:**
Direct SQLite tests using an in-memory database (`":memory:"`). Test all CRUD operations and the state machine transitions.

**State machine tests:**
Assert that `processing → processing` transition raises an exception that the router converts to `409`. Assert all other valid transitions succeed.

### Bug-to-test learning loop
- SSE buffering issue found → add `X-Accel-Buffering` header test to `test_messages.py`
- Client sees stale report → add freshness check test with specific data version change
- Concurrent session request gets wrong response → add `SESSION_BUSY` concurrency test

---

## 14. Known Constraints (Agent Guardrails)

**DO NOT** put business logic in routers — routers validate, delegate, and format responses only  
**DO NOT** call the orchestrator from anywhere except `routers/messages.py`  
**DO NOT** read or write session state from the orchestrator directly — use the store functions  
**DO NOT** return raw Python exceptions as HTTP responses — always use `APIError` model  
**DO NOT** start the orchestrator without first setting session status to `"processing"`  
**DO NOT** omit the `done` SSE event — it is required, even after errors  
**DO NOT** omit `X-Accel-Buffering: no` header on SSE responses  
**DO NOT** hardcode `CORS_ORIGINS` — always read from config  
**DO NOT** run database migrations inside request handlers — only in startup  
**DO NOT** use synchronous SQLite (`sqlite3`) in async FastAPI routes — use `aiosqlite` only  

---

## 🎓 Learning Corner

### 🏗️ Architecture Thinking

**Why the API is deliberately thin**

A common failure mode in layered architectures is "logic creep" — business logic that belongs in the domain layer slowly migrates into the API layer because it's convenient. A route handler that starts as "validate input, call service, return response" grows over time into "validate input, make some decisions about the data, call service, make more decisions, transform output, return response." The API layer in this spec is designed to resist this by having explicit "NOT responsible for" declarations and by keeping every router function under the 40-line limit.

For AI systems specifically, thin API layers are even more important because the interesting behavior lives in the agent — and you want that behavior testable in isolation, without HTTP overhead. The spec's design means you can test the entire orchestrator without starting a web server. You can test the entire API without running a real orchestrator. This separation is what makes both layers independently testable with cheap, fast unit tests.

**The session state machine as a safety mechanism**

The `SESSION_BUSY` (`409`) response when a session is already processing isn't just a technical constraint — it's a user experience and cost protection. Without it, a user who double-clicks or refreshes while the orchestrator is running would start two simultaneous Claude sessions, doubling the API cost and producing a race condition in the database. The state machine makes this impossible at the API level, before it reaches the orchestrator. State machines are underused in web APIs but extremely valuable for operations that are expensive, non-idempotent, or have meaningful intermediate states.

**Why `done` always fires, even after errors**

The `done` event being mandatory regardless of outcome is an application of the **terminal state guarantee** pattern. The client's SSE listener has a simple contract: start listening, consume events, stop listening when you see `done`. Without this guarantee, error cases require the client to implement timeout logic to know when the stream ended — "if I haven't seen an event in 30 seconds, assume it's done." That's brittle and hard to test. With the guarantee, error handling is just another event type, and the stream lifecycle is always deterministic.

### 🤖 AI Engineering Concepts

**SSE vs WebSockets for AI streaming — why SSE wins here**

Most AI streaming tutorials default to WebSockets because they're bidirectional and feel more "real-time." But bidirectionality is only valuable if the client needs to send data while the server is streaming — which is rare in AI applications. The pattern here is: user sends message (HTTP POST), server streams response (SSE). That's one-directional. SSE is simpler, reconnects automatically, and works over standard HTTP/1.1 with no upgrade handshake. Azure Container Apps handles SSE cleanly. For AI response streaming specifically — where you're pushing a sequence of tokens or events from server to client — SSE is almost always the right choice over WebSockets.

**The `X-Accel-Buffering` header and why it matters in production**

The single most common production bug with SSE deployments behind a reverse proxy (nginx, which Azure Container Apps uses) is buffering. Without `X-Accel-Buffering: no`, nginx accumulates the SSE stream into a buffer and flushes it periodically — so instead of seeing events progressively, the user sees nothing for 45 seconds and then all events at once. The header is invisible in local development (no nginx) but critical in production. This is a class of bug that's impossible to catch in unit tests and very confusing to diagnose the first time you see it. Adding it to the spec's acceptance criteria and the Known Constraints means the agent adds it unconditionally during build — not as an afterthought when the streaming is "broken in production."

**Orchestrator-agnostic API design**

The API spec references `OrchestratorEvent` types by name but doesn't import from the orchestrator module directly — instead, it serializes events to JSON and treats the report as a `dict`. This is intentional: the API layer is a boundary, not a peer of the orchestrator. If you later swap the orchestrator implementation (different model, different framework), the API doesn't change — only the orchestrator module changes. This is especially valuable for AI systems where the underlying model or framework changes frequently. The API contract (SSE events, JSON shapes, endpoint URLs) is more stable than the AI implementation behind it.

### 📦 PM/TPM Craft

**Designing for reconnection — the election day scenario**

Flow 4 in `user-flows.md` is "Quick Lookup — Election Day Morning" — a returning user on a mobile device, possibly with spotty signal. The API is explicitly designed for this: `GET /session/{id}` restores state, `GET /session/{id}/report` serves the cached guide, and if the orchestrator is still running when the client disconnects, it continues and saves the result. This design decision shows up in the spec as three lines in Section 2.2 and in AC-API-08. But it represents a meaningful product decision: we're optimizing for the user who needs their information most urgently (election day, unreliable connection) at the cost of slightly more server-side complexity (orchestrator must be connection-agnostic).

This is a pattern worth practicing: for every spec you write, identify the hardest user scenario (highest stakes, worst conditions, most important moment) and make sure the design explicitly handles it. The "election day morning on a spotty mobile connection" scenario shaped three API behaviors — the `202 Processing` response, the reconnect behavior, and the staleness detection. If you hadn't thought about it, all three would have been afterthoughts.

**API versioning from day one**

All endpoints are under `/api/v1/`. This costs nothing to add now and avoids an expensive migration later. The pattern: when you change an endpoint in a breaking way, you add `/api/v2/` endpoints and deprecate v1 over a defined period. Without versioning, every breaking change forces every client (web, mobile, any third parties) to update simultaneously — which is nearly impossible in practice. Adding the `/v1/` prefix now is a 5-minute decision that prevents a painful migration conversation in 6 months.

**Operational observability built into the spec**

The spec includes structured request logging (middleware), a health check endpoint that validates DB connectivity, startup validation that fails fast on missing config, and log output on startup. These aren't features — they're the minimum operational requirements to run a service in production without guessing what's wrong when something breaks. For AI products specifically, add to this: log token usage per request (already in the orchestrator spec), log which MCP tools were called and their latency, and log cache hit/miss rates per tool. Without this instrumentation, cost optimization and performance debugging are guesswork. With it, you can see "news-mcp cache hit rate dropped from 80% to 20% on Tuesday" and know exactly where to look.
