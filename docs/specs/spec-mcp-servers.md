# Spec: MCP Servers

**Status:** Draft v1.0  
**Component:** `mcp-servers/`  
**Depends on:** `architecture.md`, `user-flows.md`  
**Consumed by:** `spec-agent-orchestrator.md`  
**Last updated:** 2026-02-28

---

## 1. Overview

MCP servers are the **exclusive data access layer** for Ballot Guide. They are the only components that talk to external APIs, scrape web sources, or read cached data. The agent orchestrator calls them as tools — it never touches external services directly.

Three servers for MVP, all running **in-process via stdio transport** inside the API container. No separate networked services. This keeps local dev simple (no service mesh) and Azure costs near zero on scale-to-zero.

| Server | Directory | Responsibility |
|--------|-----------|---------------|
| `ballot-data-mcp` | `mcp-servers/ballot_data/` | Ballot structure, candidates, measures, campaign finance |
| `legislation-mcp` | `mcp-servers/legislation/` | Full legal text, parsed and structured |
| `news-mcp` | `mcp-servers/news/` | Recent coverage with source bias metadata |

### What MCP servers are NOT responsible for
- Summarizing or editorializing data (that is the agent's job)
- Generating user-facing text (agents do this)
- Storing session state (the API layer does this)
- Making decisions about relevance (the relevance ranker does this)

---

## 2. Shared Principles (all servers)

These apply to every tool in every server. Non-negotiable.

### 2.1 Cache-first
Every external call is cache-checked first. Cache stored in SQLite `api_cache` table. No external call is made if a valid cache entry exists.

### 2.2 Structured errors only
Tools never raise unhandled exceptions. Every failure returns a structured `ToolError` object. The agent decides how to handle it.

```python
class ToolError(BaseModel):
    error_code: str          # machine-readable, SCREAMING_SNAKE_CASE
    message: str             # human-readable, for logging
    recoverable: bool        # can the agent retry or use a fallback?
    fallback_source: str | None  # if recoverable, what to try next
```

### 2.3 Source attribution on every response
Every data object includes a `sources` list. No data without provenance.

```python
class SourceCitation(BaseModel):
    name: str                # "Ballotpedia", "Google Civic API"
    url: str                 # direct URL to the source record
    fetched_at: str          # ISO 8601
    bias_rating: str | None  # AllSides rating if applicable, else null
```

**Note:** This is the same `SourceCitation` type used in the orchestrator output schemas and frontend types. MCP servers produce it; the orchestrator passes it through unchanged. Use this name everywhere — `DataSource` is an alias that should not appear in code.

### 2.4 Data completeness signal
Every response includes a `data_completeness` field. The agent uses this to decide whether to show "Limited Data" UI state.

```python
class DataCompleteness(str, Enum):
    FULL = "full"        # all expected fields populated
    PARTIAL = "partial"  # some fields missing (e.g. fiscal impact not yet published)
    LIMITED = "limited"  # only basics available (name, type, status)
```

### 2.5 Florida-scoped for MVP
All tools validate that the request is for a Florida address or Florida ballot item. Non-Florida requests return `OUT_OF_SCOPE` error immediately without calling external APIs.

---

## 3. Server 1: `ballot-data-mcp`

**Directory:** `mcp-servers/ballot_data/`  
**Entry point:** `mcp-servers/ballot_data/server.py`

### 3.1 Tool: `get_ballot_by_address`

Resolves a voter's address or zip code to their exact precinct and returns all races and measures on their ballot.

**Input schema:**
```python
class GetBallotByAddressInput(BaseModel):
    address: str             # "123 Main St, Miami FL 33101" or "33101"
    election_id: str | None  # if None, uses next upcoming FL election
```

**Output schema:**
```python
class BallotResponse(BaseModel):
    election: ElectionSummary
    precinct: PrecinctInfo
    races: list[RaceSummary]
    measures: list[MeasureSummary]
    sources: list[SourceCitation]
    cache_hit: bool
    data_completeness: DataCompleteness

class ElectionSummary(BaseModel):
    id: str              # "FL-2026-GEN"
    name: str            # "2026 Florida General Election"
    date: str            # "2026-11-03"  ← model field is "date"; DB column is "election_date"
                         #   MCP maps: ElectionSummary(date=row["election_date"], ...)
    state: str           # "FL"

class PrecinctInfo(BaseModel):
    county: str
    district: str | None
    precinct_id: str | None

class RaceSummary(BaseModel):
    id: str
    type: str            # "governor" | "us_senate" | "state_senate" | "state_house" | "judicial_retention" | "local"
    title: str
    candidate_ids: list[str]

class MeasureSummary(BaseModel):
    id: str              # "FL-2026-A1"
    type: str            # "constitutional_amendment" | "referendum" | "bond"
    short_title: str     # "Amendment 1"
    full_title: str
```

**Error codes:**
| Code | Recoverable | Meaning |
|------|-------------|---------|
| `ADDRESS_NOT_FOUND` | true | Address couldn't be geocoded |
| `OUT_OF_STATE` | false | Address is not in Florida |
| `OUT_OF_SCOPE` | false | MVP only supports Florida |
| `NO_UPCOMING_ELECTION` | false | No scheduled FL election found |
| `CIVIC_API_UNAVAILABLE` | true | Google Civic returned 5xx |
| `RATE_LIMITED` | true | API quota exceeded |

**Data sources (in priority order):**
1. SQLite cache (`api_cache`)
2. Google Civic Information API
3. Florida Division of Elections precinct lookup (fallback)

**Cache TTL:** 24 hours  
**Cache key:** `ballot:{address_normalized}:{election_id}`

---

### 3.2 Tool: `get_measure_detail`

Returns full structured profile of a ballot measure.

**Input schema:**
```python
class GetMeasureDetailInput(BaseModel):
    measure_id: str          # "FL-2026-A1"
    include_full_text: bool = False  # full legal text — use legislation-mcp for parsing
```

**Output schema:**
```python
class MeasureDetail(BaseModel):
    id: str
    short_title: str
    full_title: str
    type: str
    summary: str | None              # Ballotpedia summary, not LLM-generated
    status: str                      # "on_ballot" | "passed" | "failed" | "withdrawn"
    election_id: str
    topic_tags: list[str]            # mapped to internal taxonomy keys
    proponent_argument: str | None   # from official FL voter guide
    opponent_argument: str | None    # from official FL voter guide
    fiscal_impact: str | None        # from FL Revenue Estimating Conference
    fiscal_impact_source: str | None
    passed: bool | None              # null=upcoming
    yes_pct: float | None
    no_pct: float | None
    full_text: str | None            # only if include_full_text=True
    ballotpedia_url: str | None
    fl_elections_url: str | None
    sources: list[SourceCitation]
    data_completeness: DataCompleteness
```

**Error codes:**
| Code | Recoverable | Meaning |
|------|-------------|---------|
| `MEASURE_NOT_FOUND` | false | ID not in any known source |
| `BALLOTPEDIA_UNAVAILABLE` | true | Ballotpedia returned 5xx |
| `OUT_OF_SCOPE` | false | Measure is not a Florida measure |

**Cache TTL:** 6 hours (upcoming), 30 days (historical/passed)  
**Cache key:** `measure:{measure_id}`

---

### 3.3 Tool: `get_candidate_detail`

Returns structured candidate profile with positions mapped to the topic taxonomy.

**Input schema:**
```python
class GetCandidateDetailInput(BaseModel):
    candidate_id: str
    topics: list[str] | None   # topic taxonomy keys to focus on. If None, fetch all.
```

**Output schema:**
```python
class CandidateDetail(BaseModel):
    id: str
    name: str
    party: str | None
    race_id: str
    bio: str | None
    photo_url: str | None
    website_url: str | None
    positions: dict[str, CandidatePosition]   # topic_key -> position
    ballotpedia_url: str | None
    sources: list[SourceCitation]
    data_completeness: DataCompleteness

class CandidatePosition(BaseModel):
    topic: str               # taxonomy key e.g. "housing"
    summary: str             # 1-2 sentence factual summary of stated position
    quote: str | None        # direct quote if available
    quote_source: str | None # URL to original quote
    source_url: str          # where this position was found
```

**Error codes:**
| Code | Recoverable | Meaning |
|------|-------------|---------|
| `CANDIDATE_NOT_FOUND` | false | ID not found in any source |
| `NO_POSITIONS_AVAILABLE` | false | Candidate found but no position data exists |

**Cache TTL:** 12 hours  
**Cache key:** `candidate:{candidate_id}`

---

### 3.4 Tool: `get_campaign_finance`

Returns campaign finance summary for a candidate or measure campaign.

**Input schema:**
```python
class GetCampaignFinanceInput(BaseModel):
    entity_id: str           # candidate_id or measure_id
    entity_type: str         # "candidate" | "measure"
```

**Output schema:**
```python
class CampaignFinanceSummary(BaseModel):
    entity_id: str
    entity_type: str
    total_raised: float | None
    total_spent: float | None
    top_donors: list[DonorSummary]   # top 5 max
    industry_breakdown: list[IndustryDonation] | None
    reporting_period: str | None
    sources: list[SourceCitation]
    data_completeness: DataCompleteness

class DonorSummary(BaseModel):
    name: str
    amount: float
    category: str | None     # "individual" | "PAC" | "corporation"

class IndustryDonation(BaseModel):
    industry: str
    amount: float
    pct_of_total: float
```

**Data sources:** OpenSecrets (federal races), FL EFIS (state/local races)  
**Cache TTL:** 24 hours  
**Cache key:** `finance:{entity_id}`

---

## 4. Server 2: `legislation-mcp`

**Directory:** `mcp-servers/legislation/`  
**Entry point:** `mcp-servers/legislation/server.py`

### 4.1 Tool: `get_measure_text`

Fetches the full official legal text of a ballot measure from the FL Legislature portal or official voter guide PDF.

**Input schema:**
```python
class GetMeasureTextInput(BaseModel):
    measure_id: str      # "FL-2026-A1"
    state: str = "FL"
```

**Output schema:**
```python
class MeasureText(BaseModel):
    measure_id: str
    raw_text: str                    # full legal text, unmodified
    source_url: str
    source_type: str                 # "html" | "pdf"
    fetched_at: str
    cache_hit: bool
```

**Cache TTL:** 30 days (legal text is immutable once filed)  
**Cache key:** `measure_text:{measure_id}`

---

### 4.2 Tool: `parse_measure_text`

Structures raw legal text into labelled sections. Does not summarize — only labels and segments.

**Input schema:**
```python
class ParseMeasureTextInput(BaseModel):
    measure_id: str
    raw_text: str
```

**Output schema:**
```python
class ParsedMeasureText(BaseModel):
    measure_id: str
    sections: list[MeasureSection]

class MeasureSection(BaseModel):
    label: str           # "findings" | "provisions" | "fiscal_impact" |
                         # "effective_date" | "definitions" | "other"
    heading: str | None  # original heading text if present
    content: str         # section text
    order: int           # position in document
```

**Parsing rules (deterministic — no LLM involved):**
- Split on numbered sections, lettered subsections, and ALL-CAPS headings
- Map to labels using keyword matching: "FINDINGS" → findings, "BE IT ENACTED" → provisions, "FISCAL IMPACT" → fiscal_impact, "EFFECTIVE DATE" → effective_date
- Anything unmatched → "other"
- Parser is regex + rule-based, not LLM-based (fast, free, deterministic)

**Cache TTL:** 30 days  
**Cache key:** `parsed_measure:{measure_id}`

---

## 5. Server 3: `news-mcp`

**Directory:** `mcp-servers/news/`  
**Entry point:** `mcp-servers/news/server.py`

### 5.1 Tool: `search_news`

Searches for recent news coverage of a ballot item or candidate.

**Input schema:**
```python
class SearchNewsInput(BaseModel):
    query: str               # e.g. "Florida Amendment 1 2026 homestead"
    date_from: str | None    # ISO date, e.g. "2026-01-01"
    date_to: str | None
    max_results: int = 5
```

**Output schema:**
```python
class NewsSearchResult(BaseModel):
    articles: list[NewsArticle]
    query_used: str
    cache_hit: bool

class NewsArticle(BaseModel):
    title: str
    url: str
    source_name: str
    published_at: str
    description: str | None  # article snippet, max 300 chars
    bias_rating: str | None  # from get_source_bias lookup
    bias_source: str | None  # "AllSides" | "AdFontes"
```

**Cache TTL:** 2 hours (news is time-sensitive)  
**Cache key:** `news:{query_hash}:{date_from}:{date_to}`

---

### 5.2 Tool: `get_source_bias`

Returns the political bias rating for a news domain.

**Input schema:**
```python
class GetSourceBiasInput(BaseModel):
    domain: str    # "miamiherald.com"
```

**Output schema:**
```python
class SourceBiasRating(BaseModel):
    domain: str
    bias_rating: str | None   # "Left" | "Lean Left" | "Center" | "Lean Right" | "Right"
    bias_source: str | None   # "AllSides" | "AdFontes"
    rating_url: str | None
    found: bool
```

**Data source:** Local JSON lookup file bundled with the server (`news/bias_ratings.json`)  
No external API call — this is a static lookup seeded from AllSides public data.  
**Cache TTL:** N/A (local static file, updated manually per release)

---

## 6. File Structure

```
mcp-servers/
├── shared/
│   ├── __init__.py
│   ├── models.py          # SourceCitation, ToolError, DataCompleteness (shared Pydantic models)
│   └── cache.py           # SQLite cache read/write helpers
├── ballot_data/
│   ├── __init__.py
│   ├── server.py          # MCP server entry point, tool registration
│   ├── tools.py           # Tool handler functions
│   └── sources/
│       ├── __init__.py
│       ├── civic.py       # Google Civic Information API client
│       ├── ballotpedia.py # Ballotpedia scraper/API client
│       ├── fl_elections.py # FL Division of Elections client
│       └── opensecrets.py # OpenSecrets + FL EFIS client
├── legislation/
│   ├── __init__.py
│   ├── server.py
│   ├── tools.py
│   └── parsers/
│       ├── __init__.py
│       ├── html_parser.py  # FL Legislature HTML pages
│       └── pdf_parser.py   # Voter guide PDFs (pdfplumber)
└── news/
    ├── __init__.py
    ├── server.py
    ├── tools.py
    ├── newsapi_client.py
    └── bias_ratings.json   # Static AllSides data
```

---

## 7. Acceptance Criteria

Each criterion is binary and testable. The agent must verify all pass before marking this spec complete.

### Cache behavior
- [ ] **AC-MCP-01:** Given a valid address that has been queried before, `get_ballot_by_address` returns `cache_hit: true` and makes zero calls to Google Civic API
- [ ] **AC-MCP-02:** Given a cached entry older than its TTL, the tool fetches fresh data and updates the cache
- [ ] **AC-MCP-03:** Cache key collisions do not occur between different tools (keys are namespaced by tool name)

### Data integrity
- [ ] **AC-MCP-04:** Every successful tool response includes at least one item in `sources` with a non-empty `url`
- [ ] **AC-MCP-05:** `data_completeness` is `"limited"` when fewer than 3 of the following are populated: summary, proponent_argument, opponent_argument, fiscal_impact
- [ ] **AC-MCP-06:** `topic_tags` on measure responses contain only values from the canonical taxonomy: `["housing", "education", "taxes", "healthcare", "environment", "public_safety", "economy", "voting_rights", "infrastructure", "senior_services"]`

### Error handling
- [ ] **AC-MCP-07:** A non-Florida address to `get_ballot_by_address` returns `error_code: "OUT_OF_STATE"` with `recoverable: false` — no external API is called
- [ ] **AC-MCP-08:** When NewsAPI returns 429 (rate limit), `search_news` returns `error_code: "RATE_LIMITED"` with `recoverable: true` — no exception is raised
- [ ] **AC-MCP-09:** All tool errors are instances of `ToolError` Pydantic model — no raw Python exceptions propagate to the caller

### Florida scope
- [ ] **AC-MCP-10:** All three servers reject requests for non-Florida data before making any external API call
- [ ] **AC-MCP-11:** `get_ballot_by_address` with zip code `"10001"` (New York) returns `OUT_OF_STATE` error

### Historical data
- [ ] **AC-MCP-12:** `get_measure_detail("FL-2022-A2")` returns data from the SQLite seed database without making any external API call (seed data covers FL 2022 General)
- [ ] **AC-MCP-13:** Historical measures with known results have `passed`, `yes_pct`, and `no_pct` populated

### Legislation parsing
- [ ] **AC-MCP-14:** `parse_measure_text` produces at least one section with `label: "provisions"` for any FL constitutional amendment text
- [ ] **AC-MCP-15:** `parse_measure_text` does not call any LLM or external API — it is purely rule-based

### Bias ratings
- [ ] **AC-MCP-16:** `get_source_bias("miamiherald.com")` returns a non-null `bias_rating`
- [ ] **AC-MCP-17:** `get_source_bias("unknowndomain123.com")` returns `found: false` and `bias_rating: null` — no error

---

## 8. Definition of Done

The agent checks every item before declaring this component complete.

- [ ] All 17 acceptance criteria pass
- [ ] Unit tests exist for every tool (happy path + at least 2 error cases each)
- [ ] Cache hit/miss tested explicitly for `ballot-data-mcp` and `legislation-mcp`
- [ ] All Pydantic models validated — no `dict` returns anywhere in tool handlers
- [ ] `ToolError` returned for every documented error code (no undocumented 500s)
- [ ] No hardcoded API keys — all credentials via environment variables
- [ ] No hardcoded FL-specific strings outside of `fl_elections.py` and config
- [ ] `bias_ratings.json` seeded with at least 20 Florida-relevant news domains
- [ ] Docker Compose `up` starts all three servers without errors
- [ ] All source files have module-level docstrings explaining purpose
- [ ] No functions longer than 40 lines (split if needed — easier for agents to reason about)
- [ ] `shared/models.py` is the single source of truth for all shared types — no duplicated model definitions across servers

---

## 9. Test Strategy

### Test file locations
```
tests/
└── mcp_servers/
    ├── conftest.py              # shared fixtures: mock API responses, test DB
    ├── test_ballot_data.py      # ballot-data-mcp tool tests
    ├── test_legislation.py      # legislation-mcp tool tests
    ├── test_news.py             # news-mcp tool tests
    └── test_shared_models.py    # shared Pydantic model validation tests
```

### Test categories

**Unit tests (no external calls):**
Every tool tested with mocked external API responses. Tests run offline, fast (<5 seconds total).

**Contract tests (shape validation):**
Every tool response validated against its Pydantic output schema. A response that passes contract tests but fails business logic tests tells you the schema is too permissive.

**Cache tests:**
- Hit: call tool twice with same input, assert second call makes zero HTTP requests
- Miss: call tool with expired cache entry, assert HTTP request is made
- TTL: assert different TTLs per tool (measure detail TTL ≠ news TTL)

**Error injection tests:**
For each external dependency, test what happens when it returns:
- 404 (not found)
- 429 (rate limited)
- 503 (unavailable)
- Malformed JSON

**Seed data smoke tests:**
`get_measure_detail("FL-2022-A2")` and three other FL 2022 measures return valid data from seed — no network required.

### Bug-to-test learning loop
When a bug is found in any MCP server:
1. Write a failing test that reproduces it **before** fixing the code
2. Fix the code until the test passes
3. Add the scenario to the relevant error table in this spec if it's not already there
4. If it's a class of bug (e.g. "missing source URL"), add a guardrail to `CLAUDE.md`

---

## 10. Known Constraints (Agent Guardrails)

These are hard rules. The agent must not violate them even if a simpler approach seems tempting.

**DO NOT** call external APIs without checking the SQLite cache first  
**DO NOT** return raw Python dicts from tool handlers — always return Pydantic model instances  
**DO NOT** summarize, editorialize, or add interpretation to returned data  
**DO NOT** raise unhandled exceptions — catch and return `ToolError`  
**DO NOT** make LLM calls inside MCP servers — that is the agent orchestrator's job  
**DO NOT** store credentials in code — use environment variables only  
**DO NOT** accept non-Florida addresses — validate and return `OUT_OF_SCOPE` immediately  
**DO NOT** create new Pydantic models in tool files — all shared models live in `shared/models.py`  
**DO NOT** write functions longer than 40 lines — split into helpers  

---

## 🎓 Learning Corner

### 🏗️ Architecture Thinking

**Why MCP servers are a strict data boundary — not just a convenience**

The decision to make MCP servers the *only* path to external data is called enforcing a **single source of truth boundary**. In traditional architectures you'd call this a data access layer or repository pattern. The principle is the same: when you centralize all data access in one place, you get caching, error handling, and retry logic in one place too — not scattered across every component that needs data.

The deeper reason this matters for AI systems specifically: the agent (the Claude orchestrator) should reason about *what data to get* and *what to do with it*, not about *how to get it*. Mixing those concerns makes agents harder to test, harder to swap out, and more likely to make inconsistent decisions about things like retry behavior or fallback sources. The MCP boundary enforces this separation structurally — the agent literally cannot call an API directly, so it can't accidentally mix concerns.

**Why in-process stdio instead of networked MCP servers**

Networked MCP servers are the "right" architecture for production at scale — each server is independently deployable, scalable, and observable. But for MVP with a single-container deployment on Azure Container Apps, networked services mean: additional containers to manage, networking configuration, service discovery, and latency on every tool call. In-process stdio means the tool call is a function call with near-zero overhead. The tradeoff is that you can't scale MCP servers independently from the API — but at MVP scale, that doesn't matter. The architecture is designed to extract servers later without changing the tool interfaces.

### 🤖 AI Engineering Concepts

**What MCP actually is and why it matters**

MCP (Model Context Protocol) is Anthropic's open standard for connecting AI models to external tools and data sources. Before MCP, every AI application had to build its own custom tool-calling layer — a different format for every model provider, no standardization, lots of duplicated work. MCP defines a standard protocol so that a tool built once (like `get_ballot_by_address`) works with any MCP-compatible model.

The practical implication for your project: if you later want to swap Claude for a different model, or use multiple models for different tasks, the MCP servers don't change. The tools are model-agnostic. This is why building MCP servers is a better investment than building custom tool functions tied to one model's API format.

**Why deterministic parsing beats LLMs for legal text segmentation**

`parse_measure_text` is deliberately rule-based rather than LLM-powered. This is a pattern worth internalizing: **use LLMs for judgment tasks, use deterministic code for structural tasks**. Splitting a legal document into sections is a structural task — there are clear signals (numbered headings, ALL-CAPS labels, "BE IT ENACTED" phrases) and the output is a set of labeled segments, not a judgment call. A regex parser is faster, free, perfectly reproducible, and testable with exact assertions. An LLM doing the same task would be slower, cost money per call, occasionally produce different outputs for the same input, and be harder to test. Knowing which tasks belong in deterministic code vs LLM calls is one of the core engineering skills in AI product development.

**Cache design in agentic systems**

Caching in AI applications is more important than in traditional apps for two reasons: (1) LLM tool calls have latency measured in seconds, not milliseconds, so a cache miss in the middle of an agent loop creates noticeable user-facing delay; (2) many agent tasks re-use the same data (the same ballot measure is looked up once per session but referenced multiple times by different agents). The TTL decisions in this spec — 6 hours for upcoming measures, 30 days for historical, 2 hours for news — reflect the rate of change of each data type. Getting these wrong in either direction has real costs: too short and you burn API quota; too long and you serve stale data on a day when a candidate drops out.

### 📦 PM/TPM Craft

**Writing acceptance criteria that AI agents can verify**

The 17 acceptance criteria in this spec follow a specific pattern: they are observable, binary, and input-specific. "AC-MCP-07: A non-Florida address to `get_ballot_by_address` returns `error_code: 'OUT_OF_STATE'` with `recoverable: false` — no external API is called" tells an agent exactly what to test, what to assert, and what success looks like. Compare this to a typical PRD acceptance criterion like "The system should handle invalid addresses gracefully" — a human engineer understands what that means, but an AI agent will either hallucinate a test or write a test that passes trivially.

The habit to build: for every behavior you care about, ask yourself "what specific input, in what specific state, produces what specific output?" Write that down instead of the abstract version. This is good PM craft regardless of whether agents or humans are building — it just becomes a hard requirement when agents are.

**Spec completeness as risk management**

Every gap in this spec is a decision the agent will make without you. Some of those decisions will be fine. Some will be architectural choices that are expensive to undo — like returning raw dicts instead of Pydantic models (looks the same in testing, breaks everything downstream when you add validation), or making LLM calls inside MCP servers (works in dev, costs 10x more at scale). The "Known Constraints" section in this spec is a direct response to this risk: it's the list of decisions that look tempting to an agent but are wrong for reasons that aren't obvious from the immediate context.

As a TPM, you can think of this as **pre-morteing the build**. Before the agent starts, you ask: "What are the most likely ways this goes wrong, and which of those can I prevent with a written rule?" The constraints section is the answer. Over time, as you learn what kinds of mistakes agents make, this section gets richer and your build sessions get cleaner.

**The "cheap model" constraint as a quality signal**

Your goal of running on auto/cheap models in Cursor is actually a quality signal for your specs and prompts. If a spec requires a frontier model to interpret correctly, the spec is underspecified. If a prompt works reliably on a cheap model, it means the instructions are clear enough that the model doesn't need to exercise much judgment to follow them — it just executes. This is the right property for build instructions. Save the expensive models for tasks that genuinely require reasoning: architectural decisions, debugging subtle issues, reviewing outputs for neutrality drift. The build tasks should be mechanical enough that a capable-but-not-brilliant model can execute them reliably given good instructions.
