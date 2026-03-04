# Ballot Guide — System Architecture

## Overview

Ballot Guide is a multi-agent AI system with MCP (Model Context Protocol) servers that personalize ballot information to each voter's stated priorities. The system is built for Florida initially, designed to be state-agnostic by architecture.

**Key decisions:**
- Claude (Anthropic) as the sole LLM for MVP — native MCP support, best instruction-following for neutrality constraints
- SQLite for MVP data layer — simple, portable, Azure File Share for persistence
- MCP servers run in-process (stdio) inside the API container — no separate networked services for MVP
- FastAPI (Python) backend, Next.js frontend
- Azure Container Apps with scale-to-zero for hosting

---

## System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     USER INTERFACE                       │
│              Next.js Chat + Report View                  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────────┐
│                   API GATEWAY                            │
│                FastAPI (Python)                          │
│         /session  /chat  /report  /health               │
└──────┬───────────────┬──────────────────────────────────┘
       │               │
       ▼               ▼
┌──────────┐   ┌───────────────────────────────────────┐
│ Session  │   │         AGENT ORCHESTRATOR             │
│  Store   │   │     Claude tool-use loop               │
│  SQLite  │   │                                        │
└──────────┘   │  ┌─────────────┐  ┌────────────────┐  │
               │  │Intake Agent │  │ Ballot Resolver│  │
               │  └─────────────┘  └────────────────┘  │
               │  ┌─────────────┐  ┌────────────────┐  │
               │  │  Measure    │  │   Candidate    │  │
               │  │  Analyst    │  │   Analyst      │  │
               │  └─────────────┘  └────────────────┘  │
               │  ┌─────────────────────────────────┐  │
               │  │      Relevance Ranker            │  │
               │  └─────────────────────────────────┘  │
               └───────────────┬───────────────────────┘
                               │ MCP protocol (stdio)
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌──────────────────┐  ┌────────────────┐  ┌───────────────┐
│  ballot-data-mcp │  │legislation-mcp │  │  news-mcp     │
│  ─────────────── │  │ ─────────────  │  │ ───────────── │
│  Ballotpedia     │  │ FL Legislature │  │ NewsAPI       │
│  Google Civic    │  │ PDF parser     │  │ AllSides bias │
│  FL Div Elections│  │ State voter    │  │ metadata      │
│  OpenSecrets     │  │ guide scraper  │  │               │
└──────────────────┘  └────────────────┘  └───────────────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │   SQLite + Azure    │
                    │   File Share        │
                    │   ballot-guide.db   │
                    │   /cache (PDFs)     │
                    └─────────────────────┘
```

---

## Component Details

### Frontend — Next.js

**Chat View** (`/`)
Conversational intake. User enters zip code and describes priorities in natural language. Responses stream via SSE. Primary UX for MVP.

**Report View** (`/report/[session-id]`)
Structured, printable ballot guide. One section per race/measure sorted by relevance to user priorities. Each section contains: plain-English summary, fiscal impact, proponent argument, opponent argument, funding sources, source links.

Session ID stored in localStorage. All state lives server-side in SQLite.

### API Gateway — FastAPI

Thin routing layer. Handles anonymous sessions (UUID), routes to orchestrator, streams responses.

```
POST /session              → create session, return session_id
POST /session/{id}/message → send user message, stream agent response (SSE)
GET  /session/{id}/report  → return structured ballot guide JSON
GET  /health               → liveness check
```

### Agent Orchestrator

Claude's native tool-use loop. MCP servers registered as tools. Sequential execution for MVP (simpler to debug than parallel).

**Orchestration flow:**
1. Intake → extract zip + priorities from conversation
2. Ballot Resolve → get exact ballot for that address
3. For each ballot item → fetch data, legislation text, news → generate neutral summary
4. Rank by relevance to user priorities
5. Assemble report

**Neutrality contract** is enforced via shared system prompt across all agents. See `neutrality-contract.md`.

### MCP Servers (3 for MVP, in-process stdio)

#### `ballot-data-mcp`
- `get_ballot_by_address(address)` — Google Civic Information API → races + measures for precinct
- `get_measure_detail(measure_id)` — Ballotpedia API → full measure profile
- `get_candidate_detail(candidate_id)` — Ballotpedia + FL Division of Elections → bio, positions
- `get_campaign_finance(candidate_id)` — OpenSecrets + FL EFIS → funding sources

#### `legislation-mcp`
- `get_measure_text(measure_id, state)` — FL Legislature portal or official voter guide PDF
- `parse_measure_text(raw_text)` — structures legal text into sections (findings, provisions, fiscal impact)
- Results cached in SQLite — legal text is immutable once filed

#### `news-mcp`
- `search_news(query, date_range)` — NewsAPI
- `get_source_bias(domain)` — AllSides/Ad Fontes rating
- Returns articles labeled by source lean; no editorial synthesis

---

## Data Layer — SQLite

### Schema

```sql
CREATE TABLE elections (
    id TEXT PRIMARY KEY,            -- "FL-2022-GEN", "FL-2026-GEN"
    state TEXT NOT NULL,
    election_type TEXT,             -- "general", "primary"
    election_date TEXT NOT NULL,
    is_historical INTEGER DEFAULT 0
);

CREATE TABLE races (
    id TEXT PRIMARY KEY,            -- "FL-2022-GOV"
    election_id TEXT REFERENCES elections(id),
    race_type TEXT,                 -- "governor", "senate", "amendment"
    title TEXT NOT NULL,
    district TEXT
);

CREATE TABLE candidates (
    id TEXT PRIMARY KEY,
    race_id TEXT REFERENCES races(id),
    name TEXT NOT NULL,
    party TEXT,
    bio TEXT,
    positions_json TEXT,            -- JSON: {topic: position}
    funding_summary_json TEXT,
    ballotpedia_url TEXT,
    fetched_at TEXT
);

CREATE TABLE measures (
    id TEXT PRIMARY KEY,            -- "FL-2022-A2"
    race_id TEXT REFERENCES races(id),
    short_title TEXT NOT NULL,
    full_title TEXT,
    measure_text TEXT,
    plain_summary TEXT,             -- LLM-generated, cached
    fiscal_impact TEXT,
    proponent_argument TEXT,
    opponent_argument TEXT,
    passed INTEGER,                 -- NULL=upcoming, 1/0=historical
    yes_pct REAL,
    no_pct REAL,
    sources_json TEXT,
    fetched_at TEXT
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now')),
    display_name TEXT,              -- optional, user-provided name
    zip_code TEXT,
    address TEXT,
    language TEXT DEFAULT 'en',     -- i18n: 'en', 'es'. MVP always 'en'
    detected_language TEXT,         -- from Accept-Language header, logged for v2
    priorities_raw TEXT,            -- original free-text input preserved
    priorities_json TEXT,           -- normalized: ["housing", "education", "taxes"]
    ballot_id TEXT REFERENCES elections(id),
    report_json TEXT,
    report_language TEXT DEFAULT 'en',
    data_version TEXT,              -- hash of ballot data at report generation time
    updated_at TEXT
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    role TEXT,                      -- "user" | "assistant"
    content TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE api_cache (
    cache_key TEXT PRIMARY KEY,
    source TEXT,
    data_json TEXT,
    fetched_at TEXT,
    expires_at TEXT
);
```

### SQLite Configuration
- WAL mode enabled on startup for concurrent reads
- Azure File Share mount at `/data/` for persistence across scale-to-zero restarts
- Litestream replication to Azure Blob Storage for backup (v2)

---

## Neutrality Architecture

### Structural (enforced in code)

Output schemas have no recommendation field. The LLM fills templates — it cannot add fields that don't exist.

```python
class MeasureSummary(BaseModel):
    plain_english_summary: str
    fiscal_impact: str
    proponent_argument: str
    opponent_argument: str
    relevance_to_priorities: str    # why this matches user's topics, not a recommendation
    sources: list[SourceCitation]
    # NO: recommendation, lean, suggested_vote
```

### Prompt (defense in depth)

Shared system prompt for all agents explicitly prohibits recommendations, requires both-sides treatment, and mandates source citation. See `neutrality-contract.md`.

### Source labeling (transparency)

Every source citation includes AllSides bias rating. System fetches from sources across the spectrum and labels them visibly.

---

## Florida-Specific Data Sources

| Source | Data | Format | Access |
|--------|------|--------|--------|
| FL Division of Elections | Candidates, results, filings | CSV, API | Free, public |
| Ballotpedia | Measures, candidate profiles | API (requires request) | Free non-commercial |
| FL Legislature (flsenate.gov) | Full measure text | HTML, PDF | Free, public |
| FL EFIS | State campaign finance | CSV, search | Free, public |
| OpenSecrets | Federal campaign finance | API | Free non-commercial |
| Google Civic Information | Address → ballot | API | Free, generous quota |
| NewsAPI | Recent coverage | API | 100 req/day free tier |

### Historical Test Data — FL 2022 General Election

Used for development and testing without live election data.

**Ballot measures:** 4 constitutional amendments (Amendment 1 school funding, Amendment 2 minimum wage, Amendment 3 marijuana, Amendment 4 voting restoration) — full text, fiscal analyses, certified results available.

**Major races:** Governor (DeSantis vs. Crist), U.S. Senate (Rubio vs. Demings), Attorney General — well-documented candidate profiles, position records, finance data.

Seed data stored in `data/seed/` and loaded via `scripts/seed_historical.py`.

---

## Infrastructure — Azure Container Apps

```
Azure Container Apps Environment
├── web (Next.js)          scale: min=0, max=3
├── api (FastAPI + MCPs)   scale: min=0, max=3
└── Azure File Share
    ├── /data/ballot-guide.db
    └── /data/cache/
```

MCP servers run as in-process stdio within the API container for MVP. Extract to separate containers in v2 if independent scaling is needed.

**Local development:** Docker Compose with the same file structure, SQLite on local filesystem.

---

## Repository Structure

```
ballot-guide/
├── apps/
│   ├── web/                        # Next.js frontend
│   │   ├── app/
│   │   │   ├── page.tsx            # Chat view
│   │   │   └── report/[id]/        # Report view
│   │   └── components/
│   │       ├── ChatInterface.tsx
│   │       ├── BallotReport.tsx
│   │       └── PriorityPicker.tsx
│   └── api/                        # FastAPI backend
│       ├── main.py
│       ├── orchestrator/
│       │   ├── agents.py
│       │   ├── prompts.py
│       │   └── schemas.py
│       ├── session/
│       └── db/
│           ├── migrations/
│           └── models.py
├── mcp-servers/
│   ├── ballot_data/
│   │   ├── server.py
│   │   └── sources/
│   │       ├── civic.py
│   │       ├── ballotpedia.py
│   │       ├── florida_elections.py
│   │       └── opensecrets.py
│   ├── legislation/
│   │   ├── server.py
│   │   └── parsers/
│   │       ├── pdf_parser.py
│   │       └── fl_legislature.py
│   └── news/
│       ├── server.py
│       └── bias_ratings.py
├── data/
│   ├── seed/
│   │   ├── fl_2022_ballot.json
│   │   ├── fl_2022_measures.json
│   │   └── fl_2022_candidates.json
│   └── .gitkeep
├── scripts/
│   ├── seed_historical.py
│   └── fetch_fl_elections.py
├── infra/
│   ├── docker-compose.yml
│   ├── Dockerfile.api
│   ├── Dockerfile.web
│   └── azure/
│       ├── container-app.bicep
│       └── file-share.bicep
├── docs/
│   ├── vision.md
│   ├── architecture.md
│   ├── neutrality-contract.md
│   ├── florida-data-sources.md
│   ├── user-flows.md               # next
│   └── testing-with-fl-2022.md
└── CLAUDE.md
```

---


---

## Topic Taxonomy

The internal topic taxonomy drives relevance ranking. All user inputs — whether from conversation starter chips or free text — are normalized to these keys by the intake agent.

| Key | Display Label | Conversation Starter Chip |
|-----|--------------|--------------------------|
| `housing` | Housing & Rent | 🏠 Housing & Rent |
| `education` | Education & Schools | 🎓 Education & Schools |
| `taxes` | Taxes & Cost of Living | 💰 Taxes & Cost of Living |
| `healthcare` | Healthcare | 🏥 Healthcare |
| `environment` | Environment & Climate | 🌿 Environment & Climate |
| `public_safety` | Public Safety & Crime | 🚔 Public Safety & Crime |
| `economy` | Jobs & Economy | 💼 Jobs & Economy |
| `voting_rights` | Voting & Elections | 🗳️ Voting & Elections |
| `infrastructure` | Infrastructure & Transportation | 🛣️ Infrastructure |
| `senior_services` | Senior Services & Medicare | 👴 Senior Services |

Free-text priorities not matching a taxonomy key are preserved in `priorities_raw` and Claude maps them to the closest key(s) at intake. If no mapping is possible, the free-text term is kept as a custom priority and used verbatim in the relevance ranker prompt.

---

## Internationalization (i18n)

Architecture supports multi-language from day one. English only in MVP.

**UI strings:** All text externalized to `/locales/{lang}.json`. No hardcoded strings in components.

**URL structure:** `/` for English (MVP). `/es/` prefix reserved for Spanish (v2).

**LLM-generated content:** Summaries generated in the session language directly — not translated post-hoc. Cached per language in `api_cache` with language suffix in cache key.

**Language detection:** `Accept-Language` header captured into `sessions.detected_language` at session creation. Not acted on in MVP — logged for v2 planning.

**Priority languages for v2:** Spanish, then Haitian Creole (significant Florida demographics).

## LLM Strategy

| Role | Model | Rationale |
|------|-------|-----------|
| Agent orchestration | Claude Sonnet 4.5 | Native MCP, best instruction-following |
| Measure/candidate summaries | Claude Sonnet 4.5 | Neutrality constraints need smart model |
| PDF/legal text extraction | Claude Sonnet 4.5 (MVP) / Gemini 2.0 Flash (v2 cost optimization) | 200K context handles FL voter guides |
| Embeddings | OpenAI text-embedding-3-small | Simple, cheap, good enough |

Claude Opus used only if Sonnet hallucinates on complex multi-measure ballots. Claude Haiku not used — neutrality constraints require a smarter model.

---

## External API Keys Required

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| Anthropic | Claude agent | Pay per token |
| Google Civic Information | Address → ballot | Yes, generous |
| Ballotpedia | Measure + candidate data | Requires approval request |
| NewsAPI | Recent coverage | 100 req/day |
| OpenSecrets | Campaign finance | Free non-commercial |

---

## Migration Path (SQLite → PostgreSQL)

When concurrent writes become a bottleneck (typically >50 concurrent users writing):
1. Schema is identical — no changes needed
2. Swap `aiosqlite` driver for `asyncpg`
3. Update connection string in environment config
4. Provision Azure Database for PostgreSQL Flexible Server
5. Run one-time data migration script

Estimated effort: 1 day.
