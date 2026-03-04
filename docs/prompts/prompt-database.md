# Build Prompt: Database

**Component:** `apps/api/db/`, `data/seed/`, `scripts/`  
**Spec:** `docs/specs/spec-database.md`  
**Depends on:** Nothing — this is the foundation. Build this before API or MCP servers.  
**Estimated sessions:** 2 focused sessions

---

## ⚠️ Before Anything Else

Read these files in order before responding:
1. `CLAUDE.md` (repo root)
2. `docs/specs/spec-database.md`

Do not write any code. Confirm you have read both files by answering:
- How many tables does the schema have, and which component owns each group?
- What does the migration runner do if a migration file has already been applied?
- What does `--dry-run` do in the seed script?
- What does `sessions.data_version` store and why?

---

## PHASE 1 — PLANNING

*No code. Planning output only.*

### Step 1: File inventory

List every file you will create, in build order. For each file state:
- Which session (A or B) it belongs to
- What it writes to (tables, files, stdout)
- Whether it has any external dependencies (libraries, network, other files)

### Step 2: Migration plan

List the two migration files and describe exactly what each contains. Then describe the migration runner logic as pseudocode — step by step, including the idempotency check and rollback behavior.

### Step 3: Seed data plan

Describe how `seed_historical.py` handles each of these three modes:
- Default (no flags): what SQL does it use? What happens on duplicate keys?
- `--replace`: what is the exact sequence of operations?
- `--dry-run`: what does it validate and what does it print?

### Step 4: Data versioning plan

Describe how `compute_data_version()` produces a deterministic hash. What inputs does it take? Why is it a pure function with no I/O?

### Step 5: Risk identification

Name the 2 most likely mistakes an agent makes when building a migration system. For each: what breaks, and what guardrail prevents it?

### ✋ STOP HERE
Present plan. Wait for approval before writing any code.

---

## PHASE 2 — BUILD

*Execute in Claude Code after plan approval. Complete sessions in order.*

---

### Session A: Schema, Migrations, and Configuration

**Goal:** The database exists, has the correct schema, and the migration system works.  
**Produces:** A working SQLite database from a fresh start.

#### Task A1: Initial Migration

Create `apps/api/db/migrations/001_initial.sql`.

Copy the canonical schema from `docs/specs/spec-database.md` Section 2 **exactly**. Every table, every column, every constraint, every default value. Then add all 7 indexes from Section 3.

Rules:
- Every `CREATE TABLE` uses `IF NOT EXISTS`
- Every `CREATE INDEX` uses `IF NOT EXISTS`
- Foreign keys use `ON DELETE CASCADE` where specified in the spec
- Column order matches the spec exactly — do not reorder

**Acceptance check — count the objects:**
```sql
-- Run this after applying the migration:
SELECT type, name FROM sqlite_master 
WHERE type IN ('table', 'index') 
AND name NOT LIKE 'sqlite_%'
AND name NOT LIKE '_migrations'
ORDER BY type, name;
```
Expected: 8 tables, 7 indexes (15 rows total, not counting `_migrations` table itself and its index).

---

#### Task A2: Seed Election Migration

Create `apps/api/db/migrations/002_seed_fl_2022.sql`.

Contains exactly one statement:
```sql
INSERT OR IGNORE INTO elections (id, state, election_type, election_date, name, is_historical)
VALUES ('FL-2022-GEN', 'FL', 'general', '2022-11-08', '2022 Florida General Election', 1);
```

That's it. Detail data (measures, candidates) is loaded by the seed script, not migrations.

---

#### Task A3: Migration Runner

Create `apps/api/db/connection.py`.

Must implement:

```python
import aiosqlite
import contextlib
import os
import glob

@contextlib.asynccontextmanager
async def get_db(db_path: str):
    """
    Async context manager for SQLite connections.
    Sets WAL mode and enables foreign keys on every open.
    Usage:
        async with get_db(DB_PATH) as db:
            await db.execute(...)
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-64000")
        await db.execute("PRAGMA temp_store=MEMORY")
        db.row_factory = aiosqlite.Row
        yield db

async def run_migrations(db_path: str) -> list[str]:
    """
    Runs all pending migrations from apps/api/db/migrations/*.sql
    in filename sort order.
    Returns list of filenames that were applied this run.
    Raises MigrationError if any migration fails.
    """
```

**Migration runner logic — implement exactly this sequence:**
```
1. Open DB connection
2. Ensure _migrations table exists (CREATE TABLE IF NOT EXISTS)
3. Get sorted list of all .sql files in migrations/ directory
4. For each file:
   a. Check if filename is in _migrations table → if yes, skip
   b. Read file contents
   c. BEGIN TRANSACTION
   d. Execute all SQL statements in the file
   e. INSERT filename into _migrations
   f. COMMIT
   g. If any step d-f fails: ROLLBACK, raise MigrationError(filename, error)
5. Return list of applied filenames
```

**`MigrationError`** — define in `apps/api/db/exceptions.py`:
```python
class MigrationError(Exception):
    def __init__(self, filename: str, cause: Exception):
        self.filename = filename
        self.cause = cause
        super().__init__(f"Migration {filename} failed: {cause}")
```

**Critical detail:** `db.row_factory = aiosqlite.Row` — set this on every connection. It makes rows accessible by column name (`row["session_id"]`) instead of index (`row[0]`). Without it, every query result needs index-based access, which is brittle and unreadable.

---

#### Task A4: SQLite Configuration Verification

Create `apps/api/db/__init__.py` — empty, just marks as package.

Verify the configuration works with this manual check:
```python
import asyncio
import aiosqlite

async def verify():
    async with get_db(":memory:") as db:
        result = await db.execute("PRAGMA journal_mode")
        row = await result.fetchone()
        assert row[0] == "wal", f"Expected wal, got {row[0]}"
        
        result = await db.execute("PRAGMA foreign_keys")
        row = await result.fetchone()
        assert row[0] == 1, f"Expected 1, got {row[0]}"
        
        print("SQLite config OK")

asyncio.run(verify())
```

---

#### Task A5: Session A Tests

Create `tests/db/conftest.py`:
```python
import pytest
import asyncio
from apps.api.db.connection import get_db, run_migrations

@pytest.fixture
async def db():
    """In-memory database with migrations applied."""
    # run_migrations must support ":memory:" as db_path
    await run_migrations(":memory:")
    async with get_db(":memory:") as db:
        yield db
```

**Note:** In-memory SQLite creates a new database each time `aiosqlite.connect(":memory:")` is called. To share one in-memory DB across migration + test, use a named in-memory DB: `file::memory:?cache=shared` with `uri=True`. Implement this in the fixture — do not use a file-based temp DB for unit tests.

Create `tests/db/test_migrations.py`.

Required tests:
```
test_fresh_db_has_all_8_tables
test_fresh_db_has_all_7_indexes
test_migrations_table_records_applied_files
test_migration_idempotent_second_run_applies_nothing
test_failed_migration_raises_migration_error
test_failed_migration_does_not_leave_partial_state
test_wal_mode_enabled
test_foreign_keys_enabled
test_cascade_delete_measures_when_race_deleted
test_cascade_delete_candidates_when_race_deleted
test_fl_2022_election_seeded_by_002_migration
```

Run: `pytest tests/db/test_migrations.py -v`  
All must pass before Session B.

---

### Session B: Seed Data and Versioning

**Goal:** FL 2022 historical data is loadable, accurate, and versioned.  
**Depends on:** Session A complete and all migration tests passing.

#### Task B1: Seed Data Files

Create `data/seed/README.md` first — document every field's source before writing the data.

Template for README:
```markdown
# Seed Data Provenance

All data is sourced from public records. Fields without a documentable
source are left null — never estimated or paraphrased.

## FL 2022 General Election

### elections / races
- Source: Florida Division of Elections
- URL: https://dos.myflorida.com/elections/

### Measures — Amendment 2 (Minimum Wage)
- measure_text: FL Division of Elections official voter guide PDF
- plain_summary: [HUMAN WRITTEN — summarized from official text]
- fiscal_impact: FL Revenue Estimating Conference report
  URL: https://edr.state.fl.us/...
- proponent_argument: Official FL voter guide, proponent statement
- opponent_argument: Official FL voter guide, opponent statement
- passed / yes_pct / no_pct: FL Division of Elections certified results
  URL: https://results.elections.myflorida.com/...
- ballotpedia_url: https://ballotpedia.org/Florida_Amendment_2,_$15_Minimum_Wage_Initiative_(2020)

[repeat for each amendment and candidate]
```

Then create `data/seed/fl_2022_election.json`, `data/seed/fl_2022_measures.json`, `data/seed/fl_2022_candidates.json` using the exact schemas from `spec-database.md` Section 5.3.

**Data accuracy rules:**
- `passed`, `yes_pct`, `no_pct` must reflect actual 2022 certified results
- `positions_json` must contain only documented public statements — no inferred positions
- `funding_summary_json` figures must come from EFIS or OpenSecrets — no estimates
- If a field cannot be sourced, use `null` — do not invent plausible-sounding content

FL 2022 Amendment results for reference (verify against official source):
- Amendment 1 (School Funding): Failed
- Amendment 2 (Minimum Wage): Passed ~60.8% yes
- Amendment 3 (Marijuana): Failed
- Amendment 4 (Voting Restoration): Passed

---

#### Task B2: Seed Script

Create `scripts/seed_historical.py`.

```python
#!/usr/bin/env python3
"""
Load FL 2022 historical election seed data into SQLite.

Usage:
    python scripts/seed_historical.py --db /data/ballot-guide.db
    python scripts/seed_historical.py --db /data/ballot-guide.db --replace
    python scripts/seed_historical.py --db /data/ballot-guide.db --dry-run
"""
```

**Implement these functions (exact signatures):**

```python
def load_seed_files() -> tuple[dict, list, list]:
    """
    Loads and validates the three seed JSON files.
    Returns (election_data, measures, candidates).
    Raises ValueError with clear message if any file is missing or malformed.
    """

def validate_seed_data(election_data: dict, measures: list, candidates: list) -> list[str]:
    """
    Validates seed data against expected schema.
    Returns list of validation errors (empty = valid).
    Does NOT write to DB.
    """

async def seed_database(db_path: str, replace: bool = False) -> dict:
    """
    Inserts seed data into the database.
    Returns counts: {"elections": 1, "races": 7, "measures": 4, "candidates": N}
    """

def main():
    """Parses args, runs appropriate mode, exits with code 0 or 1."""
```

**`--replace` sequence — implement exactly:**
```
1. Open DB
2. BEGIN TRANSACTION
3. DELETE FROM elections WHERE id = 'FL-2022-GEN'  (cascades to races, candidates, measures)
4. INSERT election, then races, then measures, then candidates
5. COMMIT
6. Print: "Replaced FL-2022-GEN: N elections, N races, N measures, N candidates"
```

**`--dry-run` sequence:**
```
1. Load and validate all seed files
2. Print validation result
3. Print what would be inserted (counts per table)
4. Print any warnings (null fields, missing sources)
5. Exit — do NOT open DB connection
```

**Sync vs async:** The seed script uses `asyncio.run(seed_database(...))` to call the async function. The `main()` function itself is sync. This is normal for CLI scripts.

---

#### Task B3: Data Versioning

Create `apps/api/db/versioning.py`.

```python
import hashlib
import json

def compute_data_version(
    election_id: str,
    race_ids: list[str],
    measure_ids: list[str],
    measure_fetched_ats: dict[str, str]
) -> str:
    """
    Computes a deterministic 16-character SHA256 hash representing
    the state of ballot data at a point in time.

    Pure function: no I/O, no randomness, no datetime.now().
    Same inputs always produce the same output.

    Args:
        election_id: e.g. "FL-2026-GEN"
        race_ids: all race IDs on the ballot
        measure_ids: all measure IDs on the ballot
        measure_fetched_ats: {measure_id: fetched_at_iso_string}

    Returns:
        16-character hex string (first 16 chars of SHA256)
    """
    version_input = {
        "election_id": election_id,
        "race_ids": sorted(race_ids),
        "measure_ids": sorted(measure_ids),
        "measure_fetched_ats": {
            k: measure_fetched_ats.get(k, "")
            for k in sorted(measure_fetched_ats.keys())
        }
    }
    canonical = json.dumps(version_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


async def check_data_freshness(session_id: str, db_path: str) -> str:
    """
    Returns "fresh", "stale", "very_stale", or "no_report".
    Logic defined in spec-database.md Section 6.2.
    """
```

**`compute_data_version` must be a pure function** — no `async`, no DB calls, no datetime.now(). The caller fetches the data and passes it in. This makes it trivially testable with exact assertions.

---

#### Task B4: Canonical Query Functions

Create `apps/api/db/queries.py`.

Implement the 5 canonical queries from `spec-database.md` Section 7 as named async functions:

```python
async def load_messages_for_session(
    session_id: str,
    db: aiosqlite.Connection,
    max_tokens: int = 20_000
) -> list[dict]:
    """
    Returns message history for a session, oldest first.
    Truncates to max_tokens by dropping oldest messages.
    Never drops message with the lowest id (first message).
    """

async def get_cached_data(
    cache_key: str,
    db: aiosqlite.Connection
) -> dict | None:
    """
    Returns parsed dict if cache hit (not expired), None otherwise.
    """

async def set_cached_data(
    cache_key: str,
    source: str,
    data: dict,
    ttl_seconds: int,
    db: aiosqlite.Connection
) -> None:
    """
    Inserts or replaces cache entry with expiry.
    """

async def get_ballot_items_for_election(
    election_id: str,
    db: aiosqlite.Connection
) -> tuple[list[dict], list[dict]]:
    """
    Returns (measures, candidates) for an election.
    """

async def find_upcoming_fl_election(
    db: aiosqlite.Connection
) -> dict | None:
    """
    Returns nearest future FL election, or None if none scheduled.
    """

async def expire_stale_cache(db: aiosqlite.Connection) -> int:
    """
    Deletes cache entries expired > 1 day ago.
    Returns count of deleted rows.
    Called on startup.
    """
```

**No inline SQL strings outside this file.** Other components import and call these functions — they do not write their own SQL.

---

#### Task B5: `.gitignore` entry

Ensure `data/ballot-guide.db` and SQLite WAL files are gitignored. Add to repo root `.gitignore` if not already present:
```
# SQLite
data/ballot-guide.db
data/ballot-guide.db-wal
data/ballot-guide.db-shm
*.db
*.db-wal
*.db-shm
```

---

#### Task B6: Session B Tests

Create `tests/db/test_seed.py`:
```
test_seed_inserts_correct_record_counts
test_seed_measures_have_passed_field_populated
test_seed_measures_have_correct_yes_pct (A2 ~60.8%)
test_seed_dry_run_exits_without_writing
test_seed_replace_clears_and_reinserts
test_seed_replace_is_atomic (simulated failure mid-replace leaves old data intact)
test_seed_candidates_positions_is_valid_json
test_seed_invalid_json_file_raises_value_error
```

Create `tests/db/test_queries.py`:
```
test_get_cached_data_returns_none_on_miss
test_get_cached_data_returns_none_on_expired_entry
test_get_cached_data_returns_data_on_valid_hit
test_set_cached_data_overwrites_existing_key
test_load_messages_returns_oldest_first
test_load_messages_never_drops_first_message
test_load_messages_truncates_to_token_budget
test_find_upcoming_election_skips_historical
test_find_upcoming_election_returns_nearest_future
test_expire_stale_cache_deletes_old_entries
test_expire_stale_cache_keeps_valid_entries
```

Create `tests/db/test_versioning.py`:
```
test_compute_data_version_deterministic
test_compute_data_version_changes_on_different_fetched_at
test_compute_data_version_insensitive_to_input_order (sorted IDs)
test_check_freshness_returns_no_report_when_no_report
test_check_freshness_returns_very_stale_after_7_days
test_check_freshness_returns_stale_on_version_mismatch
test_check_freshness_returns_fresh_for_recent_unchanged
```

Run full suite: `pytest tests/db/ -v --tb=short`  
All must pass.

---

## Final Verification

```bash
# 1. Fresh database from scratch
python scripts/seed_historical.py --db /tmp/test.db --dry-run

# 2. Apply migrations + seed
python -c "
import asyncio
from apps.api.db.connection import run_migrations
asyncio.run(run_migrations('/tmp/test.db'))
"
python scripts/seed_historical.py --db /tmp/test.db

# 3. Verify counts
sqlite3 /tmp/test.db "
SELECT 'elections', COUNT(*) FROM elections UNION ALL
SELECT 'races', COUNT(*) FROM races UNION ALL
SELECT 'measures', COUNT(*) FROM measures UNION ALL
SELECT 'candidates', COUNT(*) FROM candidates;
"
# Expected: elections=1, races=7, measures=4, candidates=6+
```

Run DoD checklist from `spec-database.md` Section 12. Check every item.

---

## If You Get Stuck

**"In-memory SQLite loses data between `run_migrations` and the test"**  
→ Two calls to `aiosqlite.connect(":memory:")` create two separate databases. Use `file::memory:?cache=shared&uri=True` to share one named in-memory DB within a test. Or use a temp file for tests that need persistence across connections.

**"Migration runner applies the same file twice"**  
→ The idempotency check queries `_migrations` by filename. Make sure `_migrations` table is created before the loop starts — not inside the loop.

**"Cascade delete test fails"**  
→ `PRAGMA foreign_keys = ON` must be set before the DELETE, not just at connection open. Verify `get_db()` sets it and the test uses `get_db()`, not a raw `aiosqlite.connect()`.

**"Seed script `--replace` leaves no data after failure"**  
→ The DELETE and INSERT must be in a single transaction. If you `COMMIT` after DELETE and then fail during INSERT, you've lost the data. Use one `BEGIN` / `COMMIT` wrapping the entire replace sequence.

**"Token truncation drops the first message"**  
→ The first message has the lowest `id`. Sort by `id ASC`, then truncate from index 1 (second message) upward — never index 0.

**"`compute_data_version` returns different hashes for the same input"**  
→ Most likely cause: dict key ordering in `json.dumps`. Use `sort_keys=True` and `separators=(",", ":")` (no spaces) for fully canonical serialization.
