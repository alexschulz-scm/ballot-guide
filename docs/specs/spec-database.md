# Spec: Database

**Status:** Draft v1.0  
**Component:** `apps/api/db/`, `data/seed/`, `scripts/`  
**Depends on:** `architecture.md`, `spec-api.md`, `spec-mcp-servers.md`  
**Consumed by:** `spec-api.md` (session store), `spec-mcp-servers.md` (api_cache), `spec-agent-orchestrator.md` (message history)  
**Last updated:** 2026-02-28

---

## 1. Overview

The database layer is SQLite for MVP. It serves three distinct purposes that must be kept conceptually separate:

| Purpose | Tables | Owner |
|---------|--------|-------|
| **Session state** | `sessions`, `messages` | API layer only |
| **Ballot data cache** | `elections`, `races`, `candidates`, `measures`, `api_cache` | MCP servers only |
| **Historical seed data** | All ballot tables (pre-populated at deploy) | Seed scripts only |

This spec covers: the canonical schema, migration system, seed data format and loading, query patterns used across the system, data versioning for staleness detection, and the migration path to PostgreSQL.

### What this spec is NOT responsible for
- SQLite connection management (defined in `spec-api.md` Section 6, implemented in `db/connection.py`)
- Session CRUD functions (defined in `spec-api.md` Section 6, implemented in `session/store.py`)
- MCP cache read/write helpers (defined in `spec-mcp-servers.md`, implemented in `mcp-servers/shared/cache.py`)

Those components own their own queries. This spec owns the **schema, migrations, seed data, and shared query patterns** they all depend on.

---

## 2. Canonical Schema

This is the single source of truth. All migration files must match this exactly. If a field appears in any spec but not here, this spec takes precedence — update here first, then the other spec.

```sql
-- ─────────────────────────────────────────────
-- BALLOT DATA (owned by MCP servers)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS elections (
    id              TEXT PRIMARY KEY,       -- "FL-2022-GEN", "FL-2026-GEN"
    state           TEXT NOT NULL,          -- "FL"
    election_type   TEXT NOT NULL,          -- "general" | "primary" | "special"
    election_date   TEXT NOT NULL,          -- ISO date "2022-11-08"
    name            TEXT NOT NULL,          -- "2022 Florida General Election"
    is_historical   INTEGER NOT NULL DEFAULT 0,  -- 1 if past election
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS races (
    id              TEXT PRIMARY KEY,       -- "FL-2022-GOV"
    election_id     TEXT NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    race_type       TEXT NOT NULL,          -- "governor" | "us_senate" | "state_senate" |
                                            -- "state_house" | "judicial_retention" | "local"
    title           TEXT NOT NULL,
    district        TEXT,                   -- "FL-26" for congressional, null for statewide
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidates (
    id              TEXT PRIMARY KEY,       -- "cand_desantis_2022"
    race_id         TEXT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    party           TEXT,                   -- "Republican" | "Democratic" | "NPA" | null
    bio             TEXT,
    positions_json  TEXT,                   -- JSON: {"housing": "...", "education": "..."}
    funding_summary_json TEXT,              -- JSON: {"total_raised": 1200000, "top_donors": [...]}
    ballotpedia_url TEXT,
    fl_elections_url TEXT,
    fetched_at      TEXT,
    data_completeness TEXT NOT NULL DEFAULT 'limited'  -- "full" | "partial" | "limited"
);

CREATE TABLE IF NOT EXISTS measures (
    id              TEXT PRIMARY KEY,       -- "FL-2022-A2"
    race_id         TEXT NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    short_title     TEXT NOT NULL,          -- "Amendment 2"
    full_title      TEXT,
    measure_text    TEXT,                   -- full legal text (may be large)
    plain_summary   TEXT,                   -- LLM-generated, cached
    fiscal_impact   TEXT,
    fiscal_impact_source TEXT,
    proponent_argument TEXT,
    opponent_argument TEXT,
    topic_tags_json TEXT,                   -- JSON array: ["housing", "taxes"]
    passed          INTEGER,                -- NULL=upcoming | 1=passed | 0=failed
    yes_pct         REAL,
    no_pct          REAL,
    sources_json    TEXT,                   -- JSON array of DataSource objects
    ballotpedia_url TEXT,
    fl_elections_url TEXT,
    fetched_at      TEXT,
    data_completeness TEXT NOT NULL DEFAULT 'limited'
);

-- ─────────────────────────────────────────────
-- API CACHE (owned by MCP servers)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS api_cache (
    cache_key       TEXT PRIMARY KEY,       -- namespaced: "ballot:33101:FL-2026-GEN"
    source          TEXT NOT NULL,          -- "ballotpedia" | "civic" | "newsapi" | etc.
    data_json       TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL           -- ISO datetime, compared with datetime('now')
);

-- ─────────────────────────────────────────────
-- SESSION STATE (owned by API layer)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,       -- UUID v4
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    display_name    TEXT,                   -- optional, max 50 chars
    zip_code        TEXT,
    address         TEXT,
    language        TEXT NOT NULL DEFAULT 'en',
    detected_language TEXT,                 -- from Accept-Language header
    priorities_raw  TEXT,                   -- original user text, preserved verbatim
    priorities_json TEXT,                   -- JSON array: ["housing", "education"]
    ballot_id       TEXT REFERENCES elections(id),
    status          TEXT NOT NULL DEFAULT 'active',  -- "active" | "processing" | "error"
    report_json     TEXT,                   -- full BallotReport JSON when complete
    report_language TEXT NOT NULL DEFAULT 'en',
    data_version    TEXT,                   -- SHA256 hash of ballot data at report time
    report_generated_at TEXT               -- ISO datetime when report was last generated
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,          -- "user" | "assistant"
    content         TEXT NOT NULL,
    token_count     INTEGER,               -- approximate, for context window management
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- MIGRATION TRACKING (internal)
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS _migrations (
    filename        TEXT PRIMARY KEY,       -- "001_initial.sql"
    applied_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Schema notes

**`measures.topic_tags_json`** — stored as JSON array text, not a separate join table. At MVP scale (hundreds of measures, not millions) the simplicity of JSON storage outweighs the query performance of normalization. If you need to filter measures by topic, use `json_each()` in SQLite.

**`messages.token_count`** — approximate token count per message, used by the orchestrator's context window management to truncate history without loading all content into Python. Populated by the API layer when saving messages. Approximate is fine — the orchestrator uses it for estimation, not exact accounting.

**`sessions.data_version`** — SHA256 hash of the concatenated IDs + `fetched_at` of all ballot data used to generate the report. When ballot data refreshes (measure text amended, candidate added), the hash changes, triggering the staleness banner.

**`ON DELETE CASCADE`** on foreign keys — if an election is deleted, all its races, candidates, and measures are deleted automatically. This simplifies re-seeding: delete the election row, re-insert everything. Used by the seed script's `--replace` flag.

---

## 3. Indexes

Required indexes for query performance. All created in `001_initial.sql`.

```sql
-- Session lookups (most frequent queries)
CREATE INDEX IF NOT EXISTS idx_sessions_status 
    ON sessions(status);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at 
    ON sessions(updated_at);

-- Message history loading (called on every orchestrator run)
CREATE INDEX IF NOT EXISTS idx_messages_session_id 
    ON messages(session_id, created_at);

-- Cache expiry check (called before every external API call)
CREATE INDEX IF NOT EXISTS idx_api_cache_expires_at 
    ON api_cache(expires_at);

-- Ballot data lookups
CREATE INDEX IF NOT EXISTS idx_races_election_id 
    ON races(election_id);

CREATE INDEX IF NOT EXISTS idx_candidates_race_id 
    ON candidates(race_id);

CREATE INDEX IF NOT EXISTS idx_measures_race_id 
    ON measures(race_id);
```

---

## 4. Migration System

### 4.1 Migration runner

Located at `apps/api/db/migrate.py`. Called during application startup before any requests are served.

**Rules:**
- Migration files are SQL files in `apps/api/db/migrations/`, named `NNN_description.sql`
- Files are executed in filename sort order (`001_` before `002_`)
- Each file is executed in a single transaction — if any statement fails, the entire migration rolls back
- Successfully applied migrations are recorded in `_migrations` table
- Already-applied migrations are skipped — running migrations twice is safe (idempotent)
- If any migration fails, startup fails with a clear error message — do not start a degraded app

```python
async def run_migrations(db_path: str) -> list[str]:
    """
    Runs all pending migrations.
    Returns list of migration filenames that were applied.
    Raises MigrationError if any migration fails.
    """
```

### 4.2 Migration files

**`001_initial.sql`** — the full canonical schema from Section 2 above, including all indexes.

**`002_seed_fl_2022.sql`** — inserts the FL 2022 historical election record and election-level metadata only (not the full measure/candidate detail — that comes from the seed script):
```sql
INSERT OR IGNORE INTO elections (id, state, election_type, election_date, name, is_historical)
VALUES ('FL-2022-GEN', 'FL', 'general', '2022-11-08', '2022 Florida General Election', 1);
```

Future migrations follow the same pattern. Never modify an existing migration file — always add a new numbered file.

### 4.3 How to add a migration

1. Create `apps/api/db/migrations/NNN_description.sql`
2. Write `CREATE TABLE IF NOT EXISTS` or `ALTER TABLE` statements
3. Test locally: delete db, restart app, confirm migration runs
4. Never edit a migration that has already been applied to any environment

---

## 5. Florida 2022 Seed Data

### 5.1 Purpose

The FL 2022 General Election seed data serves two purposes:
1. **Development** — enables building and testing the full pipeline without live election data or real API calls
2. **Testing** — all acceptance criteria referencing historical data use this seed

### 5.2 Seed data files

Located in `data/seed/`. JSON format, loaded by `scripts/seed_historical.py`.

```
data/seed/
├── fl_2022_election.json        # election + races metadata
├── fl_2022_measures.json        # 4 constitutional amendments, full detail
├── fl_2022_candidates.json      # major race candidates with positions
└── README.md                    # data sources and provenance for each field
```

### 5.3 Seed data schema

**`fl_2022_election.json`**
```json
{
  "election": {
    "id": "FL-2022-GEN",
    "state": "FL",
    "election_type": "general",
    "election_date": "2022-11-08",
    "name": "2022 Florida General Election",
    "is_historical": 1
  },
  "races": [
    {
      "id": "FL-2022-GOV",
      "election_id": "FL-2022-GEN",
      "race_type": "governor",
      "title": "Governor of Florida",
      "district": null
    },
    {
      "id": "FL-2022-SEN",
      "election_id": "FL-2022-GEN",
      "race_type": "us_senate",
      "title": "United States Senator",
      "district": null
    },
    {
      "id": "FL-2022-AG",
      "election_id": "FL-2022-GEN",
      "race_type": "state_attorney_general",
      "title": "Attorney General of Florida",
      "district": null
    },
    {
      "id": "FL-2022-A1",
      "election_id": "FL-2022-GEN",
      "race_type": "constitutional_amendment",
      "title": "Amendment 1 — School Funding",
      "district": null
    },
    {
      "id": "FL-2022-A2",
      "election_id": "FL-2022-GEN",
      "race_type": "constitutional_amendment",
      "title": "Amendment 2 — Minimum Wage",
      "district": null
    },
    {
      "id": "FL-2022-A3",
      "election_id": "FL-2022-GEN",
      "race_type": "constitutional_amendment",
      "title": "Amendment 3 — Marijuana",
      "district": null
    },
    {
      "id": "FL-2022-A4",
      "election_id": "FL-2022-GEN",
      "race_type": "constitutional_amendment",
      "title": "Amendment 4 — Voting Restoration",
      "district": null
    }
  ]
}
```

**`fl_2022_measures.json`** — one object per amendment:
```json
[
  {
    "id": "FL-2022-A2",
    "race_id": "FL-2022-A2",
    "short_title": "Amendment 2",
    "full_title": "Raising Florida's Minimum Wage",
    "measure_text": "...",
    "plain_summary": "Raises Florida minimum wage from $8.65 to $15/hour by 2026...",
    "fiscal_impact": "An indeterminate negative fiscal impact on state and local governments...",
    "fiscal_impact_source": "https://edr.state.fl.us/...",
    "proponent_argument": "...",
    "opponent_argument": "...",
    "topic_tags_json": "[\"economy\", \"taxes\"]",
    "passed": 1,
    "yes_pct": 60.8,
    "no_pct": 39.2,
    "sources_json": "[{\"name\": \"Florida Division of Elections\", \"url\": \"https://dos.myflorida.com/...\"}]",
    "ballotpedia_url": "https://ballotpedia.org/Florida_Amendment_2...",
    "fl_elections_url": "https://dos.myflorida.com/elections/...",
    "data_completeness": "full"
  }
]
```

**`fl_2022_candidates.json`** — one object per candidate:
```json
[
  {
    "id": "cand_desantis_2022",
    "race_id": "FL-2022-GOV",
    "name": "Ron DeSantis",
    "party": "Republican",
    "bio": "Ron DeSantis served as a U.S. Representative before being elected Florida Governor in 2018...",
    "positions_json": "{\"education\": \"Opposes mask mandates and critical race theory in schools. Signed HB 1467 on curriculum transparency.\", \"economy\": \"Supports reducing business regulations and eliminating state income tax.\", \"environment\": \"Signed legislation for Everglades restoration but opposed federal climate regulations.\"}",
    "funding_summary_json": "{\"total_raised\": 218000000, \"top_donors\": [{\"name\": \"Florida GOP\", \"amount\": 5000000, \"category\": \"party\"}, {\"name\": \"Ken Griffin\", \"amount\": 5000000, \"category\": \"individual\"}]}",
    "ballotpedia_url": "https://ballotpedia.org/Ron_DeSantis",
    "fl_elections_url": "https://dos.myflorida.com/elections/candidates-committees/candidate-information/...",
    "data_completeness": "full"
  }
]
```

### 5.4 Seed data provenance

Every field in the seed data must have a documented source in `data/seed/README.md`. Required sources for FL 2022:

| Data | Source |
|------|--------|
| Ballot measures text | Florida Division of Elections official voter guide |
| Amendment results | FL Division of Elections certified results |
| Fiscal impact statements | FL Revenue Estimating Conference reports |
| Pro/con arguments | Official FL voter guide proponent/opponent statements |
| Candidate bios | Ballotpedia candidate profiles |
| Candidate positions | Ballotpedia, candidate websites (archived) |
| Campaign finance | OpenSecrets (federal), FL EFIS (state) |

**Provenance rule:** If a field's source cannot be documented, the field is left null — not estimated or paraphrased.

### 5.5 Seed script

`scripts/seed_historical.py` — loads seed data into SQLite.

```python
# Usage:
python scripts/seed_historical.py --db /data/ballot-guide.db
python scripts/seed_historical.py --db /data/ballot-guide.db --replace  # delete + re-insert
python scripts/seed_historical.py --db /data/ballot-guide.db --dry-run  # validate only
```

**Script behavior:**
- `--replace`: deletes the election record (cascades to all related data) then re-inserts
- Default (no `--replace`): uses `INSERT OR IGNORE` — skips existing records
- `--dry-run`: validates JSON files against expected schema, prints what would be inserted, exits without writing
- Logs count of records inserted per table on completion
- Exits with code 1 on any error — never partially seeds

---

## 6. Data Versioning

### 6.1 The `data_version` hash

When the orchestrator generates a report, it computes a `data_version` hash and stores it in `sessions.data_version`. The hash represents the "shape" of the ballot data at report generation time.

**Hash computation:**
```python
import hashlib
import json

def compute_data_version(ballot_data: dict) -> str:
    """
    Computes a deterministic SHA256 hash of the ballot data used to generate a report.
    Input: the BallotResponse from get_ballot_by_address + all measure/candidate fetched_at values.
    """
    version_components = {
        "election_id": ballot_data["election"]["id"],
        "race_ids": sorted([r["id"] for r in ballot_data["races"]]),
        "measure_ids": sorted([m["id"] for m in ballot_data["measures"]]),
        "measure_fetched_ats": {
            m["id"]: m.get("fetched_at", "") 
            for m in ballot_data["measures"]
        }
    }
    canonical = json.dumps(version_components, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]  # first 16 hex chars, sufficient
```

### 6.2 Staleness check

Called by `check_data_freshness()` in `session/store.py`:

```python
async def check_data_freshness(session_id: str, db_path: str) -> str:
    session = await get_session(session_id, db_path)
    
    if not session["report_json"]:
        return "no_report"
    
    # Check age first
    report_age_days = (datetime.utcnow() - datetime.fromisoformat(
        session["report_generated_at"]
    )).days
    
    if report_age_days > 7:
        return "very_stale"
    
    # Check data version
    current_version = await compute_current_data_version(
        session["ballot_id"], db_path
    )
    
    if current_version != session["data_version"]:
        return "stale"
    
    return "fresh"
```

---

## 7. Query Patterns

Canonical queries used across the system. All other components must use these patterns — do not write ad-hoc SQL in routers or orchestrator stages.

### 7.1 Get session with election name

```sql
-- Used by GET /session/{id} — joins elections to populate election_name
SELECT 
    s.*,
    e.name as election_name
FROM sessions s
LEFT JOIN elections e ON s.ballot_id = e.id
WHERE s.id = ?;
```

`election_name` is `NULL` if `ballot_id` is not yet set (before Stage 2 of the orchestrator completes). The `SessionMetadataResponse` marks it `str | None` for exactly this reason.

### 7.2 Load messages for orchestrator (context window management)

```sql
-- Load messages for a session, newest first, with running token count
SELECT 
    id,
    role,
    content,
    token_count,
    created_at,
    SUM(COALESCE(token_count, 0)) OVER (ORDER BY id DESC) as cumulative_tokens
FROM messages
WHERE session_id = ?
ORDER BY id ASC;
```

The orchestrator reads this result and drops messages from the oldest end until `cumulative_tokens` fits within the context budget. The first message (lowest `id`) is never dropped.

### 7.3 Check cache before external call

```sql
SELECT data_json
FROM api_cache
WHERE cache_key = ?
  AND expires_at > datetime('now');
```

Returns `None` if no row (cache miss) or if expired (treat as miss). The MCP cache helper wraps this.

### 7.4 Get ballot items for a session

```sql
-- All measures for an election
SELECT m.*, r.race_type, r.title as race_title
FROM measures m
JOIN races r ON m.race_id = r.id
WHERE r.election_id = ?
ORDER BY r.race_type, m.short_title;

-- All candidates for an election
SELECT c.*, r.race_type, r.title as race_title
FROM candidates c
JOIN races r ON c.race_id = r.id
WHERE r.election_id = ?
ORDER BY r.race_type, c.name;
```

### 7.5 Find upcoming Florida election

```sql
SELECT id, name, election_date
FROM elections
WHERE state = 'FL'
  AND is_historical = 0
  AND election_date >= date('now')
ORDER BY election_date ASC
LIMIT 1;
```

Used by `get_ballot_by_address` when `election_id` is not specified.

### 7.6 Expire stale cache entries (maintenance)

```sql
DELETE FROM api_cache
WHERE expires_at < datetime('now', '-1 day');
```

Run this on startup to prevent unbounded cache table growth. Not critical — SQLite handles large tables fine — but good hygiene.

---

## 8. SQLite Configuration

Applied on every connection open via `apps/api/db/connection.py`:

```sql
PRAGMA journal_mode = WAL;      -- concurrent reads during writes
PRAGMA foreign_keys = ON;       -- enforce referential integrity
PRAGMA synchronous = NORMAL;    -- safe with WAL, faster than FULL
PRAGMA cache_size = -64000;     -- 64MB page cache (negative = KB)
PRAGMA temp_store = MEMORY;     -- temp tables in RAM
```

**WAL mode explanation for context:** Write-Ahead Logging allows readers to access the database while a write is in progress. Without WAL, SQLite uses exclusive locks — a write blocks all reads. For this application (many concurrent readers, occasional writes from the orchestrator), WAL mode significantly improves concurrency. It's enabled per-connection because it persists at the file level after the first connection sets it, but setting it again on each connection is harmless and makes the intent explicit.

---

## 9. File Structure

```
apps/api/db/
├── __init__.py
├── connection.py              # get_db() context manager, run_migrations()
└── migrations/
    ├── 001_initial.sql        # full schema + indexes
    └── 002_seed_fl_2022.sql   # election record insert

data/
├── seed/
│   ├── README.md              # provenance for every field
│   ├── fl_2022_election.json
│   ├── fl_2022_measures.json
│   └── fl_2022_candidates.json
└── .gitkeep                   # ballot-guide.db gitignored

scripts/
├── seed_historical.py         # loads seed data into SQLite
└── fetch_fl_elections.py      # (future) pulls live FL election data
```

---

## 10. PostgreSQL Migration Path

When you outgrow SQLite (concurrent writes at scale, typically >50 simultaneous users actively generating reports), migrating to PostgreSQL requires:

**Code changes (minimal):**
1. Replace `aiosqlite` with `asyncpg` in `connection.py`
2. Update connection string in config
3. Replace SQLite-specific syntax (see table below)

**No schema changes** — the schema is compatible with PostgreSQL as written, with these syntax adjustments:

| SQLite | PostgreSQL |
|--------|-----------|
| `TEXT` for all types | Use `UUID`, `TIMESTAMP`, `BOOLEAN` as appropriate |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` or `BIGSERIAL` |
| `datetime('now')` | `NOW()` |
| `date('now')` | `CURRENT_DATE` |
| `json_each()` | `jsonb_array_elements()` |
| `PRAGMA journal_mode=WAL` | Not needed (PostgreSQL default) |
| `PRAGMA foreign_keys=ON` | Not needed (always enforced) |

**Data migration:**
```bash
# One-time migration using sqlite3 + psql
sqlite3 ballot-guide.db .dump | sed 's/INTEGER PRIMARY KEY AUTOINCREMENT/SERIAL PRIMARY KEY/g' | psql $PG_URL
```

**Infrastructure:**
- Provision Azure Database for PostgreSQL Flexible Server (Basic tier ~$25/month)
- Update `DB_PATH` → `DATABASE_URL` in environment config
- Remove Azure File Share dependency (no longer needed for DB persistence)

**Estimated effort:** 1 engineering day. The separation of DB logic into `connection.py` and `session/store.py` makes this a contained change.

---

## 11. Acceptance Criteria

### Schema and migrations
- [ ] **AC-DB-01:** Running migrations on a fresh empty database creates all 8 tables (`elections`, `races`, `candidates`, `measures`, `api_cache`, `sessions`, `messages`, `_migrations`) plus all 7 indexes
- [ ] **AC-DB-02:** Running migrations twice on the same database produces no errors and no duplicate tables
- [ ] **AC-DB-03:** A failing migration SQL statement causes the entire migration to roll back — no partial state
- [ ] **AC-DB-04:** `PRAGMA foreign_keys = ON` — inserting a `race` with a non-existent `election_id` raises a foreign key constraint error
- [ ] **AC-DB-05:** `ON DELETE CASCADE` — deleting an election row deletes all associated races, candidates, and measures

### Seed data
- [ ] **AC-DB-06:** Running `seed_historical.py` on a fresh database inserts: 1 election, 7 races, 4 measures (amendments), 6+ candidates
- [ ] **AC-DB-07:** Running `seed_historical.py --replace` on a database with existing FL 2022 data deletes and re-inserts cleanly
- [ ] **AC-DB-08:** Running `seed_historical.py --dry-run` outputs expected insert counts without modifying the database
- [ ] **AC-DB-09:** All 4 FL 2022 amendments have `passed` field populated (not null) with correct historical results
- [ ] **AC-DB-10:** All seed candidates have `data_completeness: "full"`

### Data versioning
- [ ] **AC-DB-11:** `compute_data_version()` returns the same hash for identical inputs and different hashes when `fetched_at` changes on any measure
- [ ] **AC-DB-12:** `check_data_freshness()` returns `"very_stale"` for a report older than 7 days regardless of data changes
- [ ] **AC-DB-13:** `check_data_freshness()` returns `"stale"` when `sessions.data_version` differs from current computed version
- [ ] **AC-DB-14:** `check_data_freshness()` returns `"fresh"` for a report generated < 24 hours ago with unchanged ballot data

### Query correctness
- [ ] **AC-DB-15:** Message load query returns messages in `created_at` ascending order (oldest first)
- [ ] **AC-DB-16:** Cache query returns `None` for an expired entry even if the row exists
- [ ] **AC-DB-17:** "Find upcoming FL election" query returns the nearest future election, not a past one

### SQLite configuration
- [ ] **AC-DB-18:** After connection open, `PRAGMA journal_mode` returns `"wal"`
- [ ] **AC-DB-19:** `PRAGMA foreign_keys` returns `1` (enabled) after connection open

---

## 12. Definition of Done

- [ ] All 19 acceptance criteria pass
- [ ] `001_initial.sql` matches the canonical schema in Section 2 exactly (field by field)
- [ ] All 7 indexes created in `001_initial.sql`
- [ ] `002_seed_fl_2022.sql` inserts the election record
- [ ] `seed_historical.py` runs with `--dry-run`, `--replace`, and default mode
- [ ] All 4 FL 2022 amendments seeded with `passed`, `yes_pct`, `no_pct` populated
- [ ] `data/seed/README.md` documents source for every seeded field
- [ ] `compute_data_version()` is a pure function (no I/O, deterministic)
- [ ] All canonical query patterns from Section 7 are implemented as named functions — no inline SQL strings in other components
- [ ] `.env.example` includes `DB_PATH`
- [ ] `data/ballot-guide.db` is in `.gitignore`
- [ ] Migration runner tested: fresh DB, idempotent re-run, failure rollback

---

## 13. Test Strategy

### Test file locations
```
tests/
└── db/
    ├── conftest.py              # in-memory SQLite fixture, runs migrations
    ├── test_migrations.py       # migration runner behavior
    ├── test_seed.py             # seed script behavior
    ├── test_queries.py          # canonical query correctness
    └── test_versioning.py       # data_version hash + freshness check
```

### Test approach

**All tests use in-memory SQLite (`:memory:`)** — fast, isolated, no file cleanup needed. The migration runner must support `:memory:` as a valid `db_path`.

**Seed tests** use a temporary file database — the seed script writes to a file path, not in-memory. Use `tmp_path` pytest fixture.

### Required test cases

```
# Migrations
test_fresh_db_has_all_tables_after_migration
test_fresh_db_has_all_indexes_after_migration
test_migration_idempotent_on_second_run
test_failed_migration_rolls_back
test_migration_records_applied_in_migrations_table

# Seed data
test_seed_inserts_correct_record_counts
test_seed_dry_run_makes_no_changes
test_seed_replace_clears_and_reinserts
test_seed_measures_have_results_populated
test_seed_candidate_positions_valid_json

# Queries
test_cache_query_misses_expired_entry
test_cache_query_hits_valid_entry
test_message_load_returns_oldest_first
test_find_upcoming_election_skips_historical
test_find_upcoming_election_returns_nearest

# Versioning
test_data_version_deterministic_same_input
test_data_version_changes_on_fetched_at_update
test_freshness_very_stale_over_7_days
test_freshness_stale_on_version_mismatch
test_freshness_fresh_recent_unchanged

# SQLite config
test_wal_mode_enabled_after_get_db
test_foreign_keys_enforced_after_get_db
test_cascade_delete_removes_children
```

### Bug-to-test learning loop
- Migration fails on Azure (not locally) → add test running migration from a read-only directory
- Seed data has wrong result for an amendment → add assertion for specific `passed`/`yes_pct` values
- Cache returns expired data → add test with clock manipulation (freeze time)
- Freshness check wrong on timezone edge case → add tests with UTC boundary datetimes

---

## 14. Known Constraints (Agent Guardrails)

**DO NOT** modify existing migration files — always add a new numbered file  
**DO NOT** write inline SQL strings in routers, orchestrator stages, or MCP tools — use the named query functions  
**DO NOT** use synchronous `sqlite3` module — only `aiosqlite`  
**DO NOT** commit `ballot-guide.db` to git — it must be in `.gitignore`  
**DO NOT** store sensitive data in seed files — positions and bios are public record  
**DO NOT** estimate or paraphrase seed data fields — use null if source cannot be documented  
**DO NOT** set `PRAGMA synchronous = OFF` — risk of data corruption on crash  
**DO NOT** skip `PRAGMA foreign_keys = ON` — SQLite disables FK enforcement by default  
**DO NOT** use `INSERT OR REPLACE` in seed script default mode — use `INSERT OR IGNORE` to avoid overwriting manually-corrected data  
**DO NOT** run migrations inside request handlers — startup only  

---

## 🎓 Learning Corner

### 🏗️ Architecture Thinking

**Why three separate conceptual owners for one database**

The schema has three distinct ownership zones: session state (API layer), ballot data cache (MCP servers), and seed data (scripts). These share one SQLite file but have different access patterns, different owners, and different lifecycle rules. Session data is created and deleted by user activity. Ballot data is fetched and cached by MCP servers and rarely deleted. Seed data is inserted once at deploy and treated as read-only at runtime.

Keeping these conceptually separate — even though they live in one file — prevents a common anti-pattern: any component reading or writing any table. When a bug causes wrong data in the `measures` table, you know immediately to look at MCP servers, not the API routers. When session data is corrupted, you look at the API session store, not the seed script. Ownership clarity is a debugging accelerator.

**SQLite WAL mode — why it matters for this architecture**

Without WAL mode, SQLite uses a readers-writer lock: a write operation blocks all readers until it completes. For a single-user local app this is invisible. For a web app where multiple concurrent users are reading their ballot reports while one user's orchestrator is writing new session data, this creates lock contention that manifests as occasional 500ms-2000ms delays on read operations. WAL mode eliminates this by maintaining a separate write-ahead log: readers see a consistent snapshot of the database while writers append to the log. The trade-off is slightly more disk I/O and a small additional file (`.db-wal`). For this application, it's an unambiguous win — the read-heavy workload is exactly the pattern WAL was designed for.

**Migration systems as operational safety**

The migration system in this spec has one rule that seems overly strict at first: never modify an existing migration file, always add a new one. The reason is operational safety across environments. If you modify `001_initial.sql` after it's been applied to your production database, the migration runner sees `001_initial.sql` in the `_migrations` table and skips it — your production database doesn't get the change, your local database does (because you wiped it), and now they're inconsistent in a way that's hard to detect until something breaks. New numbered files avoid this entirely: every environment gets every migration in order, and the `_migrations` table is the audit log of what's been applied where.

### 🤖 AI Engineering Concepts

**Message history as external memory for LLMs**

The `messages` table is doing something that feels like a database concern but is actually a fundamental AI engineering pattern: **externalizing LLM memory**. Language models have no persistent state between API calls — every call starts fresh. The only way an AI assistant "remembers" previous turns of a conversation is if those turns are re-injected into the context window on each new call. The `messages` table is the persistence layer for this pattern. The `token_count` column and the context-windowed query pattern (Section 7.1) are the management layer — ensuring you don't exceed Claude's context limit as conversations grow.

This pattern generalizes to every stateful AI application: identify what the model needs to "remember" across calls, store it externally, re-inject the relevant subset at the start of each call. The "relevant subset" decision is where most of the engineering work is. For conversation history, it's the most recent N tokens. For a long-running agent task, it might be a structured task state object. The principle is the same.

**Data versioning as a trust signal in AI-generated content**

The `data_version` hash and the freshness check (`"fresh"` / `"stale"` / `"very_stale"`) address a trust problem specific to AI-generated content: the content can become outdated without anyone updating it, because it was generated once and cached. A static document ages visibly — the date is right there. An AI-generated ballot guide doesn't age visibly unless you build aging detection into the system. The staleness banner ("some information on your ballot has been updated since your last visit") is user-facing trust infrastructure: it tells the user when to be skeptical of the cached content and when to refresh. Building this at the data layer — as a hash comparison — means it's reliable and cheap. Building it at the UI layer — as a timer — would be unreliable and miss actual data changes.

### 📦 PM/TPM Craft

**Seed data as a product development accelerator**

The FL 2022 seed data isn't just a testing convenience — it's a product development strategy. Without it, every development session requires: real API keys, real network calls, real quota consumption, and real latency. With it, you can build the entire frontend, test the complete agent pipeline, and demo the product to stakeholders without touching a single external API. The 2-3 hours spent creating accurate seed data pays back many times over in faster iteration cycles and the ability to work offline.

The provenance requirement (`data/seed/README.md` documenting every field's source) is also a product decision, not just an engineering one. Ballot Guide's core promise is factual accuracy with source attribution. If the seed data has unattributed fields, you're building and testing against content that violates the product's own standards. Requiring provenance in seed data enforces the product's accuracy standards during development, not just in production.

**The "operational surface area" of a database design**

Every table, every column, and every index adds to the operational surface area of your system — the number of things that can go wrong and that someone needs to understand when debugging. A disciplined database design minimizes surface area: tables have single owners, columns have clear types and semantics, indexes are purposeful. The schema in this spec has 8 tables and 7 indexes. That's small enough that one person can hold the entire schema in their head. As the product grows (more election states, more data sources, more user features), surface area will grow — but starting small means you understand the foundation before building on it.

For TPMs specifically: owning the database spec is underrated. The database schema is the most stable artifact in a software system — it changes slowly, and changes are expensive. Understanding what's in the database, why each table and column exists, and what the access patterns are gives you a foundation for making good tradeoff decisions when engineering proposes changes: "we could add a `users` table to support accounts" is a much bigger scope change than it sounds when you understand the current architecture is stateless-by-design and adding accounts changes the privacy model, the session lifecycle, and the operational burden simultaneously.
