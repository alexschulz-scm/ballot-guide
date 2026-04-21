<!-- Generated: 2026-04-20 | Files scanned: 95+ | Token estimate: ~900 -->

# Architecture Overview

## System Diagram

```
User Browser
    |
    v
[Next.js Frontend]  (apps/web/, port 3001)
    |  POST /api/v1/session/{id}/message (SSE)
    |  GET  /api/v1/session/{id}/report
    v
[FastAPI Backend]  (apps/api/, port 8001)
    |
    +-- Routers (thin) --> Session Store (SQLite)
    |
    +-- Orchestrator Runner (5-stage pipeline)
            |
            +-- LLM Client (google-genai SDK, temp=0.1)
            |       model: gemini-2.5-flash (settings.GEMINI_MODEL)
            |       prompts: apps/api/orchestrator/prompts/*.txt
            |
            +-- MCP Tool Handlers (direct Python import, not subprocess)
                    |
                    +-- ballot_data server (4 tools)
                    |       sources: Google Civic, Ballotpedia, FL Elections, FL Finance, OpenFEC
                    |
                    +-- legislation server (2 tools)
                    |       sources: FL Legislature HTML, PDF parser
                    |
                    +-- news server (2 tools)
                            sources: NewsAPI, bias_ratings.json
```

## Data Flow

```
1. User sends message
2. Router validates session, sets status="processing", saves message
3. Runner sequences stages:
   Stage 1 (Intake)       --> LLM extracts zip + priorities
   Stage 2 (Ballot)       --> MCP resolves zip to ballot items
   Stage 3 (Analysis)     --> LLM + MCP analyze each measure/race
   Stage 4 (Ranking)      --> LLM scores items by user priorities
   Stage 5 (Report)       --> Pure sync join into BallotReport
4. Events streamed as SSE to frontend
5. Report saved to session, status="active"
6. Follow-up questions re-enter at follow_up stage (skips 1-5)
```

## Key Boundaries

- **Frontend <-> Backend:** HTTP + SSE only. Types mirrored in lib/types.ts and orchestrator/schemas.py
- **Backend <-> LLM:** All calls through llm_client.py (Gemini). No direct SDK use elsewhere
- **Backend <-> External APIs:** All calls through MCP tool handlers. Orchestrator never calls APIs directly
- **Cache layer:** SQLite api_cache table. Every external call checks cache first (shared/cache.py)

## Persistence

- **SQLite** (WAL mode, aiosqlite): sessions, messages, elections, races, candidates, measures, api_cache
- **Migrations:** apps/api/db/migrations/ (001-003), applied at startup
- **Seed data:** scripts/seed_*.py, auto-run at startup (idempotent)

## Deployment

- **Local:** Docker Compose (infra/docker-compose.yml) — api on 8001, web on 3001
- **Production:** Azure Container Apps (infra/main.bicep) — scale-to-zero, Key Vault for secrets
