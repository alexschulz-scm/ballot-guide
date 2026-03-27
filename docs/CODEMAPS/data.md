<!-- Generated: 2026-03-27 | Files scanned: 15 | Token estimate: ~700 -->

# Data Layer

## Database Schema (SQLite, DELETE journal mode)

```
_migrations (filename TEXT PK)

sessions
  session_id TEXT PK
  display_name TEXT
  language TEXT DEFAULT "en"
  detected_language TEXT
  zip_code TEXT
  priorities_json TEXT        -- JSON array of taxonomy values
  priorities_raw TEXT         -- user's original text
  ballot_id TEXT              -- FK to elections.election_id
  status TEXT DEFAULT "active" -- active|processing|error
  report_json TEXT            -- full BallotReport JSON
  data_version TEXT           -- SHA256 hash for staleness
  report_generated_at TEXT
  created_at TEXT
  updated_at TEXT

messages
  id INTEGER PK AUTOINCREMENT
  session_id TEXT FK -> sessions
  role TEXT                   -- user|assistant
  content TEXT
  token_count INTEGER         -- estimated: len(content)//4
  created_at TEXT

elections
  election_id TEXT PK
  election_name TEXT
  election_date TEXT
  state TEXT
  is_historical INTEGER

races
  race_id TEXT PK
  election_id TEXT FK -> elections
  race_type TEXT              -- governor, us_senate, state_house, etc.
  title TEXT

candidates
  candidate_id TEXT PK
  race_id TEXT FK -> races
  name TEXT
  party TEXT
  bio TEXT
  positions_json TEXT
  funding_summary_json TEXT
  ballotpedia_url TEXT
  fl_elections_url TEXT
  photo_url TEXT
  website_url TEXT

measures
  measure_id TEXT PK
  race_id TEXT FK -> races     -- shared race_type mechanism
  short_title TEXT
  full_title TEXT
  summary TEXT
  measure_text TEXT
  proponent_argument TEXT
  opponent_argument TEXT
  fiscal_impact TEXT
  fiscal_impact_source TEXT
  topic_tags_json TEXT
  sources_json TEXT
  ballotpedia_url TEXT
  fl_elections_url TEXT
  passed INTEGER              -- null=on_ballot, 1=passed, 0=failed
  yes_pct REAL
  no_pct REAL

api_cache
  cache_key TEXT PK
  source TEXT
  data_json TEXT
  created_at TEXT
  expires_at TEXT
```

## Migrations

| File | Content |
|------|---------|
| 001_initial.sql | Full schema (all tables above) |
| 002_seed_fl_2022.sql | 2022 FL General election row |
| 003_seed_fl_2024.sql | 2024 FL General election row |

Applied at startup via run_migrations(). Tracked in _migrations table.

## Seed Data

| Script | Source Data |
|--------|-----------|
| scripts/seed_historical.py | data/seed/fl_2022_*.json (election, candidates, measures) |
| scripts/seed_2024.py | data/seed/fl_2024_*.json |
| scripts/seed_2026.py | Programmatic 2026 election data |

All use INSERT OR IGNORE (idempotent). Auto-run at startup via main.py.

## Cache Strategy

- All MCP external calls check api_cache first (shared/cache.py)
- TTLs: ballot=6h, measure=12h, candidate=6h, finance=24h, legislation=7d, news=1h
- Stale entries cleaned at startup (expire_stale_cache: expired > 1 day ago)

## Data Versioning

- compute_data_version() hashes election_id + race_ids + measure_ids + fetched_ats
- check_data_freshness() returns: fresh | stale | very_stale | no_report
- very_stale = report > 7 days old; stale = data_version changed
