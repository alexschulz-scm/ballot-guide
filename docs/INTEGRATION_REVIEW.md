# Integration Review — Cross-Spec Consistency Audit

**Date:** 2026-02-28  
**Reviewed:** spec-mcp-servers.md, spec-agent-orchestrator.md, spec-api.md, spec-database.md, spec-frontend.md  
**Status:** Resolved — all issues patched below

---

## Issues Found and Resolutions

---

### Issue 1 — `ElectionSummary` and `PrecinctInfo` undefined in frontend types
**Severity:** 🔴 Build-blocker

**Where:** `spec-frontend.md` Section 6, `BallotReport` interface references `ElectionSummary` and `PrecinctInfo`, but neither type is defined in `lib/types.ts`.

**Root cause:** The orchestrator spec defines these shapes implicitly (via the MCP `BallotResponse` schema) but never names them as standalone Python models. The frontend spec references them without defining them.

**Resolution:** Add these two interfaces to `lib/types.ts` exactly matching the MCP server `BallotResponse` sub-schemas:

```typescript
export interface ElectionSummary {
  id: string;       // "FL-2026-GEN"
  name: string;     // "2026 Florida General Election"
  date: string;     // "2026-11-03"
  state: string;    // "FL"
}

export interface PrecinctInfo {
  county: string;
  district: string | null;
  precinct_id: string | null;
}
```

**Also add to Python schemas.py** in the orchestrator:
```python
class ElectionSummary(BaseModel):
    id: str
    name: str
    date: str
    state: str

class PrecinctInfo(BaseModel):
    county: str
    district: str | None
    precinct_id: str | None
```

---

### Issue 2 — `DataSource` vs `SourceCitation` name mismatch
**Severity:** 🔴 Build-blocker

**Where:** MCP servers use `DataSource` (spec-mcp-servers.md Section 2.3). The orchestrator output schemas use `SourceCitation` (spec-agent-orchestrator.md Section 3.6). The frontend types use `SourceCitation`.

**The two schemas are structurally almost identical but not quite:**

| Field | `DataSource` (MCP) | `SourceCitation` (Orchestrator/Frontend) |
|-------|--------------------|-----------------------------------------|
| `name` | ✅ | ✅ |
| `url` | ✅ | ✅ |
| `bias_rating` | ✅ | ✅ |
| `fetched_at` | ✅ | ✅ |

They are identical in structure — the names just diverged across specs.

**Resolution:** Standardise on `SourceCitation` everywhere. MCP servers produce `SourceCitation` objects (rename `DataSource` → `SourceCitation` in spec-mcp-servers.md). The orchestrator passes them through unchanged. This is a name-only change — no field changes.

Update `mcp-servers/shared/models.py`:
```python
# Rename DataSource → SourceCitation throughout
class SourceCitation(BaseModel):
    name: str
    url: str
    bias_rating: str | None
    fetched_at: str
```

---

### Issue 3 — `CandidateAnalysis.positions` type mismatch
**Severity:** 🔴 Build-blocker

**Orchestrator schema** (spec-agent-orchestrator.md Section 3.3):
```python
positions: dict[str, str]   # topic_key -> 1-sentence position summary
```

**MCP `CandidateDetail`** (spec-mcp-servers.md Section 3.3):
```python
positions: dict[str, CandidatePosition]   # topic_key -> CandidatePosition object
```

**Frontend type** (spec-frontend.md Section 6):
```typescript
positions: Record<string, string>
```

So the MCP returns rich `CandidatePosition` objects, but the orchestrator schema and frontend both expect plain strings. The orchestrator's `candidate_analyst.py` stage is responsible for the flattening — it receives `CandidatePosition` objects from MCP and produces plain strings for `CandidateAnalysis`.

**Resolution:** This is intentional data transformation, not a bug — but it needs to be explicit in the orchestrator spec. Add this note to `spec-agent-orchestrator.md` Section 3.3:

> **Positions flattening:** The MCP `get_candidate_detail` tool returns `CandidatePosition` objects with `summary`, `quote`, and `source_url` fields. The `candidate_analyst` stage extracts `CandidatePosition.summary` for each topic and stores it as a plain string in `CandidateAnalysis.positions`. The quote and source_url fields are used to populate `sources` list items. The flattening happens in Claude's analysis step — the prompt instructs Claude to write one-sentence summaries from the position data.

No code changes needed — just document the transformation explicitly.

---

### Issue 4 — `top_donors` type mismatch
**Severity:** 🟡 Runtime bug risk

**MCP `CampaignFinanceSummary`** (spec-mcp-servers.md Section 3.4):
```python
top_donors: list[DonorSummary]   # list of objects: {name, amount, category}
```

**Orchestrator `CandidateAnalysis`** (spec-agent-orchestrator.md Section 3.3):
```python
top_donors: list[str]   # max 3, formatted: "Name ($Amount)"
```

**Frontend `CandidateAnalysis`** (spec-frontend.md Section 6):
```typescript
top_donors: string[]
```

Same pattern as Issue 3 — MCP returns structured objects, orchestrator stores formatted strings. The `candidate_analyst` stage formats `DonorSummary` → `"Name ($Amount)"` string during analysis.

**Resolution:** Explicit in the orchestrator candidate_analysis prompt (already there: "top_donors: top 3 by amount, formatted 'Name ($Amount)'"). Add the same clarifying note to spec-agent-orchestrator.md Section 3.3:

> **Donor formatting:** `get_campaign_finance` returns `DonorSummary` objects with `name`, `amount`, and `category` fields. The stage formats the top 3 as `"Name ($Amount)"` strings — e.g. `"Ken Griffin ($5,000,000)"`. Formatting happens in Claude's output, not in post-processing code.

---

### Issue 5 — Orchestrator writes session state but the API spec owns the store functions
**Severity:** 🟡 Architecture ambiguity

**The orchestrator spec** (stage diagrams) says:
- Stage 1 "Writes: session.zip_code, session.priorities"
- Stage 2 "Writes: session.ballot_id"
- Stage 5 "Writes: session.report_json"

**The API spec** says all session writes go through `session/store.py` functions. The orchestrator receives `db_path` and is supposed to call the store functions.

**The gap:** the orchestrator spec never says *how* it calls the store functions. Does it import from `session/store.py`? That creates a circular-ish dependency (orchestrator inside `apps/api/orchestrator/` importing from `apps/api/session/store.py`).

**Resolution:** This is fine as long as `session/store.py` is importable from orchestrator code (same package). Clarify with this rule in CLAUDE.md:

> The orchestrator calls `session/store.py` functions directly for session writes. It does NOT write to SQLite directly. Import path: `from apps.api.session.store import update_session_after_intake` etc. This is not a circular dependency — the store module has no import from the orchestrator.

---

### Issue 6 — `done` event missing `timestamp` field
**Severity:** 🟡 Minor inconsistency

**Orchestrator `OrchestratorEvent` base class** has `timestamp: str` on all events. The `DoneEvent` inherits this.

**API spec SSE example** (spec-api.md Section 2.2):
```json
{"event_type":"done","session_id":"...","timestamp":"..."}
```
✅ Includes timestamp.

**API messages router** (spec-api.md Section 3.4 code):
```python
yield f"data: {json.dumps({'event_type': 'done', 'session_id': session_id})}\n"
```
❌ Does NOT include timestamp — it's a raw dict, not an event model.

**Frontend `DoneEvent` type** (spec-frontend.md Section 6):
```typescript
export interface DoneEvent {
  event_type: "done";
  session_id: string;
}
```
❌ No `timestamp` field — inconsistent with other event types.

**Resolution:** Fix in two places:

1. Update `spec-api.md` messages router to use the event model:
```python
done_event = {"event_type": "done", "session_id": session_id, "timestamp": datetime.utcnow().isoformat()}
yield f"data: {json.dumps(done_event)}\n"
```

2. Add `timestamp` to frontend `DoneEvent`:
```typescript
export interface DoneEvent {
  event_type: "done";
  session_id: string;
  timestamp: string;
}
```

---

### Issue 7 — `ElectionSummary` field name: `date` vs `election_date`
**Severity:** 🟡 Silent data bug

**MCP `ElectionSummary`** (spec-mcp-servers.md Section 3.1):
```python
class ElectionSummary(BaseModel):
    id: str
    name: str
    date: str        # ← "date"
    state: str
```

**Database `elections` table** (spec-database.md Section 2):
```sql
election_date   TEXT NOT NULL,   -- ← "election_date"
```

These are different things — the DB column is `election_date`, the API/orchestrator model field is `date`. This is fine as long as the MCP server maps correctly when reading from SQLite. But it needs to be explicit.

**Resolution:** Add a mapping note to spec-mcp-servers.md Section 3.1:

> **Field mapping:** The `elections` table stores `election_date`. The `ElectionSummary` model exposes it as `date`. The MCP server performs this mapping when constructing the response: `ElectionSummary(date=row["election_date"], ...)`.

---

### Issue 8 — `sessions.election_name` doesn't exist in the DB schema
**Severity:** 🟡 Runtime bug

**API spec `SessionMetadataResponse`** (spec-api.md Section 2.4) returns:
```json
{
  "election_name": "2026 Florida General Election"
}
```

**Database `sessions` table** (spec-database.md Section 2) has:
```sql
ballot_id   TEXT REFERENCES elections(id)
```

`ballot_id` is stored, but `election_name` is not. The `GET /session/{id}` handler needs to join against the `elections` table to get the name.

**Resolution:** The session store `get_session()` function should join to get `election_name`:

```sql
SELECT s.*, e.name as election_name
FROM sessions s
LEFT JOIN elections e ON s.ballot_id = e.id
WHERE s.id = ?
```

Add this join to the canonical query in spec-database.md Section 7, and note it in spec-api.md:

> `election_name` in `SessionMetadataResponse` is derived via JOIN against `elections.name` on `sessions.ballot_id`. It is not stored directly on the `sessions` table.

---

### Issue 9 — `build_report_summary` references `report.session_id` but `ReportCompleteEvent` wraps a full `BallotReport`
**Severity:** 🟢 Minor

**spec-frontend.md** `buildReportSummary` function navigates to `/report/${report.session_id}`.

**`BallotReport.session_id`** exists in the orchestrator schema ✅ — this is fine. Just confirming the field is there.

No action needed.

---

### Issue 10 — `Header.tsx` component listed in structure but never described
**Severity:** 🟢 Minor spec gap

`spec-frontend.md` Section 5 lists `components/shared/Header.tsx` but Section 3 (Chat View layout) and the prompt never describe what it contains.

**Resolution:** Add to `prompt-frontend.md` Task D7 (Root Layout):

> Create `apps/web/components/shared/Header.tsx` — renders the "Ballot Guide" wordmark and tagline. Used in `ChatView` only (the Report View has its own `ReportHeader`). Keep it simple: wordmark in heading font, tagline in body font, no navigation links.

---

## Summary Table

| # | Severity | Specs affected | Fix type |
|---|----------|---------------|----------|
| 1 | 🔴 Blocker | frontend ↔ orchestrator | Add missing type definitions |
| 2 | 🔴 Blocker | mcp ↔ orchestrator ↔ frontend | Rename DataSource → SourceCitation |
| 3 | 🔴 Blocker | mcp ↔ orchestrator | Document intentional flattening |
| 4 | 🟡 Risk | mcp ↔ orchestrator | Document intentional formatting |
| 5 | 🟡 Risk | orchestrator ↔ api | Clarify import pattern |
| 6 | 🟡 Risk | orchestrator ↔ api ↔ frontend | Add timestamp to done event |
| 7 | 🟡 Risk | mcp ↔ database | Document field mapping |
| 8 | 🟡 Risk | api ↔ database | Add JOIN to session query |
| 9 | 🟢 Minor | frontend | No action needed |
| 10 | 🟢 Minor | frontend prompt | Add Header.tsx description |

**3 build-blockers, 5 runtime bug risks, 2 minor.**  
All resolved above. Apply fixes to specs before building.

---

## Recommended Build Order

Given these dependencies, build in this sequence:

```
1. Database (Spec 4)
   └── Run migrations, seed FL 2022 data
   └── Verify schema correct before anything writes to it

2. MCP Servers (Spec 1)
   └── Depends on: database (api_cache table)
   └── Test with seed data before orchestrator uses them

3. Orchestrator (Spec 2)
   └── Depends on: MCP servers (calls them as tools), database (session writes)
   └── Test end-to-end against FL 2022 seed data

4. API Layer (Spec 3)
   └── Depends on: orchestrator (calls run_orchestrator), database (session store)
   └── Test SSE stream with orchestrator

5. Frontend (Spec 5)
   └── Depends on: API layer (all endpoints)
   └── Start with mock API, wire to real API last
```

**Do not build in parallel.** Each layer needs the one below it to test correctly. A frontend built against a mock API will work in tests but may have subtle type mismatches when wired to the real API — the integration issues above are exactly the kind of thing that surfaces at that moment.

---

## Before Handing to Cursor

For each spec's build prompt, prepend this instruction at the top:

> **Before starting:** Read `docs/INTEGRATION_REVIEW.md` and apply all patches marked for this component before writing any code.

This ensures the agent sees the corrections before building, not after.
