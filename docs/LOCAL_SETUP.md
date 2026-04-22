# Local Development Setup

Step-by-step guide to run the Ballot Guide app on your machine.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend API + MCP servers |
| Node.js | 18+ | Next.js frontend |
| npm | 9+ | Frontend dependencies |
| Git | any | Version control |
| Docker *(optional)* | 24+ | Containerized backend |

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd ballot-guide
```

Copy the environment template and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```bash
# ─── Google Gemini ───────────────────────────
GEMINI_API_KEY=YOUR_KEY_HERE
GEMINI_MODEL=gemini-2.0-flash

# ─── External APIs (MCP servers) ─────────────
GOOGLE_CIVIC_API_KEY=YOUR_KEY_HERE
NEWSAPI_KEY=YOUR_KEY_HERE
OPENFEC_API_KEY=YOUR_KEY_HERE        # Free: https://api.data.gov/signup/

# ─── Database ────────────────────────────────
DB_PATH=data/ballot-guide.db

# ─── Application ─────────────────────────────
APP_VERSION=1.0.0
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:3000"]

# ─── Development ─────────────────────────────
MOCK_EXTERNAL_APIS=false
MOCK_LLM=false

# ─── Per-source mock overrides ───────────────
# Only checked when MOCK_EXTERNAL_APIS=false.
# Google Civic returns 400 for 2026 — mock it until real data exists.
MOCK_CIVIC_API=true
MOCK_OPENFEC_API=false
MOCK_FL_FINANCE_API=false
MOCK_BALLOTPEDIA_API=false
MOCK_FL_ELECTIONS_API=false
MOCK_NEWSAPI=false
MOCK_LEGISLATION_API=false
```

> **Tip:** Set `MOCK_CIVIC_API=true` and leave others `false` to use real
> OpenFEC and NewsAPI data while mocking only Google Civic (which has no
> 2026 election data yet).

---

## 2. Option A — Run without Docker (recommended for development)

### 2a. Backend (FastAPI)

```bash
# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

Start the API server:

```bash
uvicorn apps.api.main:app --reload --port 8001
```

On first startup the server will:
1. Validate all required environment variables (crashes if any are missing)
2. Export API keys to `os.environ` for MCP servers
3. Run database migrations (`apps/api/db/migrations/001–003`)
4. Seed FL 2022, FL 2024, and FL 2026 election data automatically

The API is now running at **http://localhost:8001**.

Verify with:

```bash
curl http://localhost:8001/health
```

### 2b. Frontend (Next.js)

In a separate terminal:

```bash
cd apps/web
npm install
npm run dev
```

The frontend is now running at **http://localhost:3000**.

It proxies `/api/v1/*` requests to the backend via Next.js rewrites
(configured in `apps/web/next.config.ts`, defaults to `http://localhost:8001`).

> **If the backend runs on a different port**, set `API_URL` before starting:
> ```bash
> API_URL=http://localhost:8000 npm run dev
> ```

### 2c. Open the app

Navigate to **http://localhost:3000** in your browser. You should see the
chat interface with an election dropdown in the header.

---

## 3. Option B — Run with Docker

Docker Compose runs the API in a container. You still run the frontend
natively (the Dockerfile only covers the API).

```bash
# From repo root
docker compose -f infra/docker-compose.yml up --build
```

This will:
- Build the API image from `infra/Dockerfile`
- Mount a persistent volume at `/data` for the SQLite database
- Expose the API on **http://localhost:8000**
- Run health checks every 30 seconds

Then start the frontend separately:

```bash
cd apps/web
npm install
API_URL=http://localhost:8000 npm run dev
```

> **Note:** When using Docker, the API runs on port 8000, so set
> `API_URL=http://localhost:8000` for the frontend and
> `CORS_ORIGINS=["http://localhost:3000"]` in `.env`.

---

## 4. Seed data (manual)

Migrations auto-seed election data on first startup. If you need to
re-seed or replace data manually:

```bash
# FL 2022 historical election
python scripts/seed_historical.py --db data/ballot-guide.db

# FL 2024 historical election
python scripts/seed_2024.py --db data/ballot-guide.db

# FL 2026 upcoming election
python scripts/seed_2026.py --db data/ballot-guide.db
```

Flags:
- `--replace` — drop and re-insert data for that election
- `--dry-run` — print what would be inserted without writing

---

## 5. Run tests

All tests run offline — external APIs are mocked automatically.

```bash
# All Python tests (MCP servers + API)
python -m pytest tests/ -v

# MCP server tests only
python -m pytest tests/mcp_servers/ -v

# API tests only
python -m pytest tests/api/ -v

# Frontend tests
cd apps/web && npm test
```

---

## 6. Per-source mock flags

The mock system has two tiers:

| Flag | Scope | Effect |
|------|-------|--------|
| `MOCK_EXTERNAL_APIS=true` | Master override | Mocks **all** external APIs (used by tests) |
| `MOCK_CIVIC_API=true` | Per-source | Mocks only Google Civic API |
| `MOCK_OPENFEC_API=true` | Per-source | Mocks only OpenFEC |
| `MOCK_FL_FINANCE_API=true` | Per-source | Mocks only FL campaign finance |
| `MOCK_BALLOTPEDIA_API=true` | Per-source | Mocks only Ballotpedia |
| `MOCK_FL_ELECTIONS_API=true` | Per-source | Mocks only FL Division of Elections |
| `MOCK_NEWSAPI=true` | Per-source | Mocks only NewsAPI |
| `MOCK_LEGISLATION_API=true` | Per-source | Mocks only legislation text fetching |

- When `MOCK_EXTERNAL_APIS=true`, all sources are mocked regardless of per-source flags.
- When `MOCK_EXTERNAL_APIS=false`, each per-source flag is checked independently.

---

## 7. Available elections

The app ships with three seeded elections:

| Election | Date | Type |
|----------|------|------|
| 2026 Florida General Election | 2026-11-03 | Upcoming |
| 2024 Florida General Election | 2024-11-05 | Historical |
| 2022 Florida General Election | 2022-11-08 | Historical |

Users select an election from the dropdown in the header. Historical
elections show a "(Historical)" suffix. Switching elections creates a new
session.

---

## 8. Project structure

```
ballot-guide/
├── apps/
│   ├── api/                  # FastAPI backend + orchestrator
│   │   ├── main.py           # App entry point, lifespan, middleware
│   │   ├── config.py         # pydantic-settings configuration
│   │   ├── db/               # SQLite connection, migrations
│   │   ├── routers/          # HTTP endpoints (sessions, messages, reports, elections)
│   │   ├── orchestrator/     # 5-stage pipeline (intake → report)
│   │   └── session/          # Session state management
│   └── web/                  # Next.js frontend
│       └── src/
│           ├── components/   # React components (chat, report, shared)
│           ├── hooks/        # useSession, useSSEStream
│           ├── lib/          # api.ts, i18n, types
│           └── locales/      # en.json (all UI strings)
├── mcp_servers/              # Python MCP server package
│   ├── shared/               # Shared models, cache, mock config
│   ├── ballot_data/          # Ballot, candidate, measure, finance data
│   ├── legislation/          # Legal text fetching and parsing
│   └── news/                 # News search and bias ratings
├── data/
│   └── seed/                 # Election seed data (JSON)
├── scripts/                  # Seed scripts
├── tests/                    # Python + frontend tests
├── infra/                    # Docker, Azure IaC
├── docs/                     # Specs, prompts, architecture
├── .env.example              # Environment variable template
└── CLAUDE.md                 # Project rules and constraints
```

---

## Troubleshooting

**App crashes on startup with missing key error**
All API keys are required. Check `.env` has values for `GEMINI_API_KEY`,
`GOOGLE_CIVIC_API_KEY`, `NEWSAPI_KEY`, and `OPENFEC_API_KEY`.

**Frontend shows blank page / network errors**
Ensure `CORS_ORIGINS` in `.env` matches the frontend URL
(e.g., `["http://localhost:3000"]`). Check that the API is running and
`API_URL` points to the correct backend port.

**"No elections" in dropdown**
The database may not have been seeded. Check that migrations ran on startup
(look for "Applied migration" in API logs). Or run seed scripts manually
(see Section 4).

**Google Civic API returns 400**
Expected for 2026 elections (no data yet). Set `MOCK_CIVIC_API=true` in
`.env`. Historical elections (2022, 2024) use seed data and don't call
Google Civic.

**Tests fail with import errors**
Ensure you're running from the repo root with the virtual environment
activated. The test conftest sets environment variables before imports.
