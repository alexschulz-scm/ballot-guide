# Ballot Guide — Architecture & Technical Decisions

> Updated: 2026-03-04 — reflects what is actually deployed in the MVP.

---

## Overview

Ballot Guide is an AI-powered voter information tool for Florida. Users enter their address and priorities; the system returns a personalized, factual, source-cited summary of everything on their ballot. It never recommends how to vote.

**Key architectural choices:**
- Claude Sonnet (Anthropic) as the sole LLM — native MCP support, best instruction-following for neutrality constraints
- SQLite with DELETE journal mode on ephemeral (EmptyDir) storage
- MCP servers run as in-process Python imports inside the API container
- FastAPI (Python) backend, Next.js (TypeScript) frontend
- Azure Container Apps (Consumption plan) with internal/external ingress split

---

## Deployed System Diagram

```
Internet (HTTPS)
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  Azure Container Apps Environment (Consumption plan)        │
│  ballot-guide-dev-env  ·  eastus                            │
│                                                             │
│  ┌───────────────────────┐    ┌──────────────────────────┐  │
│  │  ballot-guide-web     │    │  ballot-guide-api         │  │
│  │  Next.js standalone   │───▶│  FastAPI + Claude agent   │  │
│  │  node:20-alpine       │    │  python:3.11-slim         │  │
│  │  Port 3000            │    │  Port 8000                │  │
│  │  External ingress     │    │  Internal ingress only    │  │
│  │  0.25 vCPU / 0.5 GB  │    │  0.25 vCPU / 0.5 GB      │  │
│  │  Scale 0-2 replicas  │    │  Scale 0-3 replicas       │  │
│  └───────────────────────┘    └────────────┬─────────────┘  │
│                                            │                │
│                                  ┌─────────▼──────────┐     │
│                                  │  EmptyDir volume    │     │
│                                  │  /data/ballot-      │     │
│                                  │    guide.db         │     │
│                                  │  SQLite (DELETE      │     │
│                                  │   journal mode)     │     │
│                                  └────────────────────┘     │
│                                                             │
│  ┌───────────────────────┐                                  │
│  │  Log Analytics        │                                  │
│  │  30-day retention     │                                  │
│  └───────────────────────┘                                  │
└─────────────────────────────────────────────────────────────┘
         ▲
         │ Images pulled from
┌────────┴──────────────┐
│  Azure Container      │
│  Registry (Basic SKU) │
│  ballotguidedevacr    │
└───────────────────────┘
         ▲
         │ docker build + push
┌────────┴──────────────┐
│  GitHub Actions CI/CD │
│  test → build → deploy│
└───────────────────────┘
```

---

## Request Flow

```
Browser
  │ HTTPS
  ▼
ballot-guide-web (Next.js)
  │ Internal HTTP rewrite: /api/v1/* → http://ballot-guide-api/api/v1/*
  ▼
ballot-guide-api (FastAPI)
  │
  ├── POST /api/v1/session                → create session
  ├── POST /api/v1/session/{id}/message   → SSE stream
  ├── GET  /api/v1/session/{id}/report    → structured JSON report
  ├── GET  /api/v1/elections              → list elections
  └── GET  /health                        → liveness check
  │
  ▼ (on /message)
Orchestrator Runner (5 stages, sequential)
  │
  ├── Stage 1: Intake        → extract zip + priorities from conversation
  ├── Stage 2: Ballot Resolve → match address to election ballot
  ├── Stage 3: Analysis       → per-item measure/candidate analysis
  ├── Stage 4: Ranking        → relevance-rank by user priorities
  └── Stage 5: Report         → assemble final report (pure sync)
  │
  ├── Claude Sonnet (Anthropic API) — reasoning & summarization
  │     Temperature: 0.1 (fixed)
  │
  ├── MCP: ballot_data → Google Civic API, OpenFEC API
  ├── MCP: legislation → bill text parsing
  └── MCP: news → NewsAPI
  │
  └── SQLite: sessions, elections, api_cache, reports, messages
```

The frontend is the **only public endpoint**. The API container has internal-only ingress — it's reachable within the Container Apps environment but not from the internet. No CORS needed since all browser requests go through the frontend proxy.

---

## Technical Decisions & Rationale

### 1. EmptyDir Volume Instead of Azure File Share

**What we tried:** Azure File Share (SMB) mounted at `/data` for SQLite persistence.

**What happened:** Persistent `database is locked` errors in production. Azure File Share uses SMB protocol, which does not support the POSIX file locking that SQLite requires — even in single-writer mode.

**What we did:** Switched to `EmptyDir` (ephemeral container-local storage). Data is lost on scale-to-zero or restart, but:
- Election data auto-seeds at startup from baked-in scripts (3 elections: FL-2022, FL-2024, FL-2026 — loads in <1s)
- Session data is transient by design
- Manual re-seed available via `seed.yml` workflow if needed

**Future path:** Azure Container Apps disk mounts with proper POSIX locking, or migration to PostgreSQL when concurrent writes exceed SQLite's capacity.

### 2. SQLite DELETE Journal Mode (Not WAL)

**What we tried:** WAL mode (the default recommendation for concurrent read/write).

**What happened:** WAL creates `-wal` and `-shm` sidecar files that need POSIX locking. Even after switching to EmptyDir, we standardized on DELETE mode for simplicity and compatibility.

**Production PRAGMAs:**
```sql
PRAGMA busy_timeout = 5000;     -- 5s wait on lock contention
PRAGMA journal_mode = DELETE;    -- no sidecar files
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;     -- balanced durability/speed
PRAGMA cache_size = -64000;      -- 64 MB page cache
PRAGMA temp_store = MEMORY;      -- temp tables in RAM
```

Stale WAL/SHM files are cleaned up in `_cleanup_wal_files()` before each connection open, as a safety net.

### 3. Next.js Standalone Build with Build-Time API_URL

**The constraint:** Next.js `rewrites()` in `next.config.ts` are evaluated at build time and baked into the server bundle. The API URL must be known during `npm run build`, not at container runtime.

**Implementation:** The `web.Dockerfile` accepts `ARG API_URL=http://ballot-guide-api` and sets it as `ENV` before the build step. The internal Container Apps DNS name (`http://ballot-guide-api`) is the default.

**Multi-stage build:**
1. **deps** — `node:20-alpine`, `npm ci`
2. **builder** — copy source, set `API_URL`, `npm run build`
3. **runner** — copy only `.next/standalone` + `.next/static` + `public`, run `node server.js`

Result: ~100 MB production image.

### 4. ACR-First Deploy Order

**The problem:** Bicep container app definitions reference specific image tags. If images don't exist in the registry when the container app is created, deployment fails with `MANIFEST_UNKNOWN`.

**Solution:** The CI/CD pipeline:
1. Ensure ACR exists (idempotent `az acr create`)
2. `az acr login`
3. Build and push both images (tagged with git SHA + `latest`)
4. Deploy Bicep (which references the just-pushed images)

### 5. MCP Servers as In-Process Python Imports

MCP tool handlers are imported as regular Python functions — not run as separate stdio subprocesses.

**Why:** Simpler deployment (single container), easier testing (monkeypatch imports), lower latency (no subprocess IPC). The MCP SDK's stdio transport is designed for editor integrations; in a server deployment, direct imports are more appropriate.

### 6. Frontend Proxy (No Direct API Access)

All `/api/v1/*` requests from the browser are rewritten by Next.js to the internal API. Benefits:
- No CORS configuration needed (same-origin from browser perspective)
- API keys never exposed to browser network tab
- Single public endpoint simplifies firewall rules and DNS
- Container Apps internal DNS handles service discovery automatically

### 7. Scale-to-Zero with Auto-Seed

Azure Container Apps Consumption plan with `minReplicas: 0` — containers scale to zero when idle, eliminating compute costs during inactive periods. The free tier (180,000 vCPU-seconds/month) covers ~200 hours of active use.

**The blocker solved:** EmptyDir is wiped on scale-down, so the database starts empty on cold start. Solution: auto-seed at startup. The API lifespan manager runs migrations then calls seed scripts via `_auto_seed()` in `main.py` — three elections are loaded: FL-2022-GEN (historical), FL-2024-GEN (historical), FL-2026-GEN (upcoming). All seed data is baked into the Docker image (`data/seed/` + `scripts/`). Seed functions use `INSERT OR IGNORE` for idempotency. Total seed data: ~45KB, loads in <1s.

**Cold start latency:** 15-30s (container pull + Python startup + migrations + seed). Acceptable for MVP.

### 8. Election Auto-Selection

The `ElectionSelector` component auto-selects the first election on page load. Without this, the `<select>` element visually shows the first option but never fires `onChange`, creating sessions with `ballot_id=NULL` — which causes "No upcoming FL election found" errors downstream.

---

## Infrastructure as Code (Bicep)

```
infra/
├── main.bicep                    # Root orchestrator — wires all modules
├── Dockerfile                    # API container (python:3.11-slim)
├── web.Dockerfile                # Web container (node:20-alpine, multi-stage)
├── modules/
│   ├── registry.bicep            # ACR (Basic SKU, admin enabled)
│   ├── environment.bicep         # Container Apps Environment + Log Analytics
│   ├── api.bicep                 # API container app (internal, scale 0-3)
│   └── web.bicep                 # Web container app (external, scale 0-2)
└── parameters/
    └── dev.bicepparam            # Dev environment parameter values
```

**Module dependency order:** registry → environment → api + web (parallel)

**Secrets:** Passed as `@secure()` Bicep parameters via CLI `--parameters` flags, stored as GitHub Actions secrets, injected as Container Apps secrets (not env vars).

---

## CI/CD Pipeline

### `deploy.yml` — Build & Deploy

**Triggers:** Push to `main`, manual `workflow_dispatch`

```
┌──────────┐        ┌─────────────────────┐
│  test     │───────▶│  build-and-deploy    │
│  pytest   │        │                     │
│  (mocked) │        │  1. az login        │
└──────────┘        │  2. Ensure ACR      │
                    │  3. Build & push    │
                    │     API + Web imgs  │
                    │  4. Deploy Bicep    │
                    │  5. Print URLs      │
                    └─────────────────────┘
```

- **Test job:** `pytest tests/ -v` with `MOCK_EXTERNAL_APIS=true MOCK_CLAUDE=true`
- **Image tags:** `{git-sha-7-chars}` + `latest`
- **Auth:** Azure service principal (`AZURE_CREDENTIALS` secret)

### `seed.yml` — Database Seeding (Manual Override)

**Trigger:** Manual `workflow_dispatch` with election selector (all / 2022 / 2024 / 2026)

Runs seed scripts inside the running API container via `az containerapp exec`. With auto-seed on startup, this workflow is a fallback for manual re-seeding or adding new election data mid-lifecycle without restarting the container.

### Required GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `AZURE_CREDENTIALS` | Service principal JSON (clientId, clientSecret, subscriptionId, tenantId) |
| `ANTHROPIC_API_KEY` | Claude API access |
| `GOOGLE_CIVIC_API_KEY` | Google Civic Information API |
| `NEWSAPI_KEY` | News search |
| `OPENFEC_API_KEY` | Campaign finance data |

---

## Component Details

### Frontend — Next.js

| Route | Purpose |
|-------|---------|
| `/` | Chat interface — conversational intake + SSE streaming |
| `/report/[session-id]` | Structured, printable ballot guide |

- All user-facing strings via `t()` from `lib/i18n.ts` (no hardcoded text)
- All API calls centralized in `lib/api.ts` (no `fetch` in components)
- SSE parsing isolated in `useSSEStream` hook
- Session state in `useSession` hook (localStorage for session ID and election ID)
- Report items displayed in API-provided relevance order (no re-sorting)

### Backend — FastAPI

Thin routing layer. Validates input, delegates to store/orchestrator, formats response.

- `aiosqlite` for all async database access (never synchronous `sqlite3`)
- Migrations + auto-seed run at startup only (never in request handlers)
- All SSE responses include `X-Accel-Buffering: no` header
- `done` event is always the last SSE event (via `finally` block)
- Session status transitions enforced in `update_session_status`

### Agent Orchestrator

Sequential 5-stage pipeline in `runner.py`:

1. **Intake** — extract zip code + priorities from user message
2. **Ballot Resolver** — match zip to election ballot (uses pre-selected election from session)
3. **Analysis** — per-item measure and candidate analysis via MCP tools + Claude
4. **Relevance Ranking** — score items by alignment with user priorities
5. **Report Assembly** — pure sync function, no Claude/MCP calls

Rules:
- Stages never call each other — only `runner.py` sequences them
- All Claude calls go through `claude_client.py` (centralized)
- Prompts live in `.txt` files under `apps/api/orchestrator/prompts/`
- Temperature: 0.1 (fixed, not configurable)
- Follow-up mode: if session already has a report, subsequent messages get conversational answers

### MCP Servers (3, in-process)

| Server | Tools | External APIs |
|--------|-------|---------------|
| `ballot_data` | get_ballot, get_candidates, get_measures, get_finance | Google Civic, OpenFEC, FL Division of Elections |
| `legislation` | get_measure_text, parse_measure_text | FL Legislature portal |
| `news` | search_news, get_source_bias | NewsAPI, AllSides |

All external calls check `api_cache` in SQLite first. No LLM calls inside MCP servers.

---

## Data Layer — SQLite

### Key Tables

| Table | Purpose |
|-------|---------|
| `elections` | Election records (FL-2024-GEN, etc.) with `is_historical` flag |
| `races` | Races within elections (governor, senate, amendments) |
| `candidates` | Candidate profiles, positions, funding |
| `measures` | Ballot measures with pro/con arguments, fiscal impact |
| `sessions` | User sessions with zip, priorities, ballot_id, report |
| `messages` | Conversation history per session |
| `api_cache` | Cached external API responses with TTL |
| `_migrations` | Applied migration filenames (idempotency tracking) |

### Migration System

- SQL files in `apps/api/db/migrations/`, applied in alphabetical order at startup
- Each migration wrapped in transaction with rollback on error
- Idempotent: checks `_migrations` table before applying

---

## Neutrality Architecture

### Structural Enforcement (in code)

Output schemas have no recommendation field. The LLM fills constrained Pydantic models — it cannot add fields that don't exist.

**Forbidden output fields** (any schema, any file):
`recommendation`, `suggested_vote`, `lean`, `preferred_candidate`, `vote_for`

**Forbidden relevance_reason phrases:**
"help you", "benefit you", "support your goal", "align with your values", "better for you", "improve your"

### Prompt Enforcement (defense in depth)

Shared system prompt prohibits recommendations, requires both-sides treatment, mandates source citation. See `docs/neutrality-contract.md`.

### Display Rules

- Labels are "For" and "Against" — never "Support"/"Oppose" or "Yes side"/"No side"
- `proponent_argument` and `opponent_argument` always render as a pair
- Missing candidate positions render explicit text — never silently omitted
- No red/blue partisan color scheme — civic palette only

---

## Topic Taxonomy

The canonical list of priority topics. Only these values are valid in `topic_tags` and `priorities_json`:

```
housing, education, taxes, healthcare, environment,
public_safety, economy, voting_rights, infrastructure, senior_services
```

Free-text priorities not matching a taxonomy key are preserved in `priorities_raw` and mapped to the closest key(s) at intake. Unmappable terms are kept as custom priorities.

---

## Known Limitations (MVP)

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Ephemeral storage** | Database lost on scale-to-zero | Auto-seed on startup recreates all data in <1s |
| **Cold start latency** | 15-30s on first request after idle | Acceptable for MVP; add warm-up ping if needed |
| **Session data lost on scale-down** | Active sessions expire when containers idle | Sessions are transient; users restart naturally |
| **No custom domain** | `*.azurecontainerapps.io` URL | Add custom domain + cert for public launch |
| **No CDN** | Static assets served from container | Add Azure Front Door when traffic warrants |
| **Google Civic API mocked** | Ballot lookup uses mock data | Set `MOCK_CIVIC_API=false` when ready |
| **Florida only** | Other states rejected at intake | Architecture is state-agnostic; add state configs |
| **English only** | i18n architecture exists but unused | Spanish + Haitian Creole planned for v2 |
| **30-day log retention** | PerGB2018 SKU minimum | Increase for production |

---

## Cost Estimate (MVP, minimal traffic)

| Resource | SKU | Estimated Monthly Cost |
|----------|-----|----------------------|
| Container Apps (2 containers, scale-to-zero) | Consumption | ~$0 (free tier) |
| Container Registry | Basic | ~$5 |
| Log Analytics (30-day retention) | Per-GB | ~$2-5 |
| **Total** | | **~$7-10/month** |

*Free tier: 180,000 vCPU-seconds + 360,000 GiB-seconds/month. At ~2 hours/day of active use, both containers stay within free tier. Costs increase with sustained traffic.*

---

## Local Development

```bash
# Full stack with Docker Compose
docker compose up

# Or individually:
# API (port 8001)
cd apps/api && uvicorn apps.api.main:app --port 8001

# Web (port 3001, proxies /api/v1/* to localhost:8001)
cd apps/web && npm run dev
```

Environment variables loaded from `.env` at project root. See `.env.example` for required values.

---

## Production Readiness Checklist

Before public launch, update:
- [ ] `MOCK_CIVIC_API` → `false`
- [ ] `CORS_ORIGINS` → production domain(s)
- [ ] ACR SKU → Standard (geo-replication)
- [ ] Log retention → 90+ days
- [ ] Container resources → increase CPU/RAM based on load testing
- [ ] Max replicas → enable autoscaling (2-5 replicas)
- [ ] Custom domain + TLS certificate
- [ ] Service principal → migrate to managed identity
- [ ] Persistent storage → Azure Disk mount or PostgreSQL migration
- [ ] Add application monitoring (Application Insights)
- [ ] Rotate service principal credentials
