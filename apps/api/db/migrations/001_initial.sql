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
    sources_json    TEXT,                   -- JSON array of SourceCitation objects
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

-- ─────────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────────

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
