# Build Prompt: API Layer

**Component:** `apps/api/`  
**Spec:** `docs/specs/spec-api.md`  
**Depends on:** MCP Servers ✅, Agent Orchestrator ✅  
**Estimated sessions:** 3 focused sessions

---

## ⚠️ Before Anything Else

Read these files in order before responding:
1. `CLAUDE.md` (repo root)
2. `docs/specs/spec-agent-orchestrator.md` — specifically Section 4 (Event Stream) and the `run_orchestrator` signature
3. `docs/specs/spec-api.md`

Do not write any code. Confirm you have read all files by answering:
- What are the 5 API endpoints and their HTTP methods?
- What header is required on SSE responses and why?
- What happens if a second message request arrives while the session is `"processing"`?
- What is the last SSE event in every stream, including error streams?

---

## PHASE 1 — PLANNING

*No code. Planning output only.*

### Step 1: File inventory

List every file you will create in `apps/api/`, in build order. For each file:
- What does it import from other components (orchestrator, MCP servers, shared models)?
- Does it write to SQLite? If yes, which tables?
- Does it have async functions? Sync functions? Both?

### Step 2: SSE implementation plan

Describe exactly how you will implement the SSE stream in `routers/messages.py`. Answer:
- Which FastAPI response class handles SSE?
- How does the route function consume the orchestrator's async generator?
- Where does the `done` event get emitted?
- What happens to the generator if the client disconnects?

### Step 3: State machine plan

Draw the session state transitions as a table:

| Current state | Action | New state | HTTP response if invalid |
|--------------|--------|-----------|------------------------|
| `active` | receive message | `processing` | — |
| `processing` | receive message | — | `409 SESSION_BUSY` |
| ... | ... | ... | ... |

Then describe where in the code each transition is enforced. Is it in the router, the session store, or both?

### Step 4: Migration plan

Describe how database migrations work in this project:
- Where do migration SQL files live?
- When do they run?
- What happens if migration fails at startup?
- How do you test that a migration ran correctly?

### Step 5: Risk identification

Name the 3 most likely failure modes specific to the API layer (not the orchestrator). For each:
- What breaks?
- How do you detect it in tests?
- What guardrail prevents it?

### ✋ STOP HERE
Present plan. Wait for approval.

---

## PHASE 2 — BUILD

*Execute in Claude Code after plan approval. Complete sessions in order.*

---

### Session A: Foundation — Config, DB, Models

**Goal:** Everything the routers depend on. No routing logic yet.

#### Task A1: Configuration

Create `apps/api/config.py`.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_PATH: str = "/data/ballot-guide.db"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    ANTHROPIC_API_KEY: str
    GOOGLE_CIVIC_API_KEY: str
    NEWSAPI_KEY: str
    OPENSECRETS_API_KEY: str
    MOCK_EXTERNAL_APIS: bool = False
    MOCK_CLAUDE: bool = False

    def validate_required(self):
        # Pydantic already validates but call this at startup for explicit logging
        pass

    class Config:
        env_file = ".env"

settings = Settings()
```

Also create `.env.example` at repo root listing all variables with empty values and comments explaining each.

---

#### Task A2: Database Connection

Create `apps/api/db/connection.py`.

```python
import aiosqlite
import contextlib

@contextlib.asynccontextmanager
async def get_db(db_path: str):
    """
    Async context manager for SQLite connections.
    Enables WAL mode and foreign keys on every connection.
    Usage: async with get_db(DB_PATH) as db: ...
    """

async def run_migrations(db_path: str) -> None:
    """
    Runs all .sql files in apps/api/db/migrations/ in filename order.
    Tracks completed migrations in a _migrations table.
    Skips already-applied migrations.
    Raises on SQL error — startup fails if migration fails.
    """
```

**WAL mode must be set on every connection open, not just once:**
```python
await db.execute("PRAGMA journal_mode=WAL")
await db.execute("PRAGMA foreign_keys=ON")
```

---

#### Task A3: Initial Migration

Create `apps/api/db/migrations/001_initial.sql`.

Copy the full schema from `docs/architecture.md` Section "Data Layer — SQLite". Include all tables:
- `elections`
- `races`
- `candidates`
- `measures`
- `sessions`
- `messages`
- `api_cache`

Each `CREATE TABLE` statement must use `IF NOT EXISTS`.

---

#### Task A4: API Models

Create `apps/api/models.py`.

Define all request and response Pydantic models from `spec-api.md` Section 4:
- `CreateSessionRequest`
- `SendMessageRequest`
- `CreateSessionResponse`
- `SessionMetadataResponse`
- `ReportResponse`
- `HealthResponse`
- `APIError`

Include all field validators exactly as specified. `APIError` must be used for ALL non-200 responses — no bare `HTTPException` with string detail.

---

#### Task A5: Session Store

Create `apps/api/session/store.py`.

Implement all 9 functions from `spec-api.md` Section 6. Exact signatures must match.

**Critical implementation detail for `update_session_status`:**
```python
async def update_session_status(session_id, status, db_path):
    VALID_TRANSITIONS = {
        "active": ["processing"],
        "processing": ["active", "error"],
        "error": ["processing"],
    }
    current = await get_session(session_id, db_path)
    if current is None:
        raise SessionNotFoundError(session_id)
    if status not in VALID_TRANSITIONS.get(current["status"], []):
        raise InvalidTransitionError(current["status"], status)
    # ... perform update
```

Define `SessionNotFoundError` and `InvalidTransitionError` as custom exceptions in `apps/api/session/exceptions.py`. Routers catch these and convert to HTTP responses.

---

#### Task A6: Session A Tests

Create `tests/api/test_session_store.py`.

Use in-memory SQLite (`:memory:`) for all tests. Run migration first in each test's setup.

Required tests:
```
test_create_session_returns_uuid
test_create_session_writes_to_db
test_get_session_returns_none_for_unknown_id
test_update_session_status_valid_transition
test_update_session_status_invalid_transition_raises
test_processing_to_processing_raises_invalid_transition
test_save_and_load_messages_round_trip
test_load_messages_never_drops_first_message
test_save_report_persists_json
test_get_report_returns_none_when_missing
test_check_data_freshness_returns_fresh_for_new_report
test_migration_runs_idempotently  (run twice, assert no error)
test_wal_mode_enabled_after_connection
```

Run: `pytest tests/api/test_session_store.py -v`  
All must pass before Session B.

---

### Session B: Routers

**Goal:** All 5 HTTP endpoints.  
**Depends on:** Session A complete.  
**Rule:** Routers are thin. If a function exceeds 40 lines, extract logic to a helper.

#### Task B1: Sessions Router

Create `apps/api/routers/sessions.py`.

Implements:
- `POST /api/v1/session` → `create_session`
- `GET /api/v1/session/{session_id}` → `get_session_metadata`

For `create_session`:
```python
@router.post("/session", status_code=201, response_model=CreateSessionResponse)
async def create_session(body: CreateSessionRequest = CreateSessionRequest()):
    # 1. Extract detected_language from Accept-Language header
    # 2. Call session store create_session()
    # 3. Return CreateSessionResponse
    # On DB error: raise HTTPException with APIError body
```

For `get_session_metadata`:
```python
@router.get("/session/{session_id}", response_model=SessionMetadataResponse)
async def get_session_metadata(session_id: str):
    # 1. Call session store get_session()
    # 2. If None: return 404 with APIError(error_code="SESSION_NOT_FOUND")
    # 3. Count messages for message_count
    # 4. Return SessionMetadataResponse
```

---

#### Task B2: Messages Router (SSE)

Create `apps/api/routers/messages.py`.

This is the most important router. Implement carefully.

```python
@router.post("/session/{session_id}/message")
async def send_message(session_id: str, body: SendMessageRequest):
    # 1. Validate session exists → 404 if not
    # 2. Check session status → 409 if "processing"
    # 3. Set session status to "processing"
    # 4. Save user message to messages table
    # 5. Return StreamingResponse with event_generator
    
    return StreamingResponse(
        event_generator(session_id, body.content, settings.DB_PATH),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
```

Implement `event_generator` as an async generator:
```python
async def event_generator(session_id: str, message: str, db_path: str):
    try:
        async for event in run_orchestrator(session_id, message, db_path):
            yield f"event: {event.event_type}\n"
            yield f"data: {event.model_dump_json()}\n"
            yield "\n"
            # Handle session state updates from events
            if event.event_type == "report_complete":
                await update_session_status(session_id, "active", db_path)
    except Exception as e:
        logger.error(f"Orchestrator failed for session {session_id}: {e}")
        error_event = ErrorEvent(
            event_type="error",
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat(),
            error_code="ORCHESTRATOR_ERROR",
            message="An unexpected error occurred. Please try again.",
            recoverable=True
        )
        yield f"event: error\n"
        yield f"data: {error_event.model_dump_json()}\n"
        yield "\n"
        await update_session_status(session_id, "error", db_path)
    finally:
        # Always send done — no matter what
        yield f"event: done\n"
        yield f"data: {json.dumps({'event_type': 'done', 'session_id': session_id})}\n"
        yield "\n"
```

**The `finally` block guaranteeing `done` is non-negotiable. Do not remove it.**

---

#### Task B3: Reports Router

Create `apps/api/routers/reports.py`.

```python
@router.get("/session/{session_id}/report", response_model=ReportResponse)
async def get_report(session_id: str):
    # 1. Get session → 404 SESSION_NOT_FOUND if missing
    # 2. If status == "processing" → 202 with processing message
    # 3. Get report → 404 REPORT_NOT_READY if None
    # 4. Check freshness
    # 5. Return ReportResponse
```

---

#### Task B4: Health Router

Create `apps/api/routers/health.py`.

```python
@router.get("/health", response_model=HealthResponse)
async def health_check():
    try:
        async with get_db(settings.DB_PATH) as db:
            await db.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"
    
    status = "ok" if db_status == "ok" else "degraded"
    status_code = 200 if status == "ok" else 503
    
    return Response(
        content=HealthResponse(...).model_dump_json(),
        status_code=status_code,
        media_type="application/json"
    )
```

---

#### Task B5: Main App

Create `apps/api/main.py`.

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Ballot Guide API", version=settings.APP_VERSION)

# CORS
app.add_middleware(CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Routers
app.include_router(health_router)                        # no prefix
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(messages_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")

# Startup
@app.on_event("startup")
async def startup():
    # Exactly as specified in spec-api.md Section 8
    # Order matters — do not reorder
```

---

#### Task B6: Session B Tests

Create `tests/api/test_sessions.py`, `tests/api/test_messages.py`, `tests/api/test_reports.py`.

Use `TestClient` from `fastapi.testclient` for sync tests. Use `httpx.AsyncClient` for SSE tests.

**Required tests for sessions:**
```
test_create_session_returns_201
test_create_session_with_display_name
test_create_session_with_invalid_language_returns_422
test_get_session_metadata_returns_200
test_get_session_unknown_id_returns_404_with_error_code
```

**Required tests for messages (SSE):**
```
test_send_message_returns_event_stream_content_type
test_send_message_has_x_accel_buffering_header
test_send_message_stream_ends_with_done_event
test_send_message_error_stream_still_ends_with_done_event
test_send_message_empty_content_returns_422
test_send_message_too_long_returns_422
test_send_message_processing_session_returns_409
test_send_message_unknown_session_returns_404
```

**Required tests for reports:**
```
test_get_report_returns_200_with_report
test_get_report_no_report_yet_returns_404_report_not_ready
test_get_report_processing_returns_202
test_get_report_stale_data_returns_stale_freshness
test_get_report_unknown_session_returns_404_session_not_found
```

For SSE tests, use a mock orchestrator that yields a fixed sequence of events:
```python
async def mock_orchestrator(session_id, message, db_path):
    yield IntakeCompleteEvent(...)
    yield BallotFoundEvent(...)
    yield ReportCompleteEvent(...)
```

---

### Session C: Startup, Middleware, and Verification

**Goal:** Complete the application — startup sequence, request logging, and end-to-end verification.

#### Task C1: Logging Middleware

Create `apps/api/middleware/logging.py`.

Structured request logging. Log on every request:
```python
{
    "timestamp": "...",
    "method": "POST",
    "path": "/api/v1/session/xxx/message",
    "status_code": 200,
    "duration_ms": 45231,
    "session_id": "xxx"   # extracted from path if present
}
```

Use Python's `logging` module with JSON formatting. Do not use `print()`.

---

#### Task C2: Startup Test

Create `tests/api/test_startup.py`.

```
test_startup_fails_without_anthropic_api_key
test_startup_runs_migration_on_empty_db
test_startup_wal_mode_confirmed
test_startup_succeeds_with_all_env_vars
test_health_returns_200_when_db_ok
test_health_returns_503_when_db_missing
```

---

#### Task C3: End-to-End API Test

Create `tests/api/test_e2e.py`.

Full flow test using mock orchestrator and in-memory SQLite:

```
test_full_session_lifecycle:
  1. POST /session → get session_id
  2. POST /session/{id}/message → consume SSE stream
  3. Assert all required events received in order
  4. GET /session/{id}/report → assert report returned
  5. GET /session/{id} → assert has_report: true
```

---

## Final Verification

```bash
pytest tests/api/ -v --tb=short
```

All tests pass. Then run DoD checklist from `spec-api.md` Section 12.

**Manual check:** Start the app with `docker compose up`. Send a real request with `curl`:
```bash
curl -N -X POST http://localhost:8000/api/v1/session/TEST_ID/message \
  -H "Content-Type: application/json" \
  -d '{"content": "I live in 33101 and care about housing"}'
```
Confirm you see events streaming in the terminal, ending with `done`.

---

## If You Get Stuck

**"SSE events aren't streaming — they all arrive at once"**  
→ Check `X-Accel-Buffering: no` header is present. Also check if you're running behind nginx locally. Try `curl -N` (--no-buffer) to see raw output.

**"FastAPI `StreamingResponse` isn't async-compatible with my generator"**  
→ Ensure `event_generator` is defined with `async def` and uses `yield`, not `return`. `StreamingResponse` accepts async generators natively.

**"Session status transition test is failing"**  
→ Check that `update_session_status` reads current status before checking valid transitions. Don't trust the status the caller thinks it is — always read from DB.

**"Migration ran but tables are missing"**  
→ Add `await db.commit()` after migration SQL execution. SQLite requires explicit commit even in auto-commit-looking scenarios.

**"CORS is blocking the frontend"**  
→ Check `CORS_ORIGINS` in config includes the exact frontend URL including protocol and port. `http://localhost:3000` ≠ `http://127.0.0.1:3000`.

**"The `done` event isn't being sent after an error"**  
→ The `finally` block in `event_generator` must be at the same level as the `try`. If it's nested inside a condition, it won't always fire. Flatten it.
