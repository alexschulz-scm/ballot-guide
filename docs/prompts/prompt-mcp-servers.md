# Build Prompt: MCP Servers

**Component:** `mcp-servers/`  
**Spec:** `docs/specs/spec-mcp-servers.md`  
**Phase:** See section headers below  
**Estimated sessions:** 3-4 focused sessions (one per server + shared layer)

---

## ⚠️ Before Anything Else

Read these files in order before responding:
1. `CLAUDE.md` (repo root)
2. `docs/specs/spec-mcp-servers.md`

Do not write any code until instructed. Confirm you have read both files by summarizing in 3 bullet points what this component does and what its most important constraints are.

---

## PHASE 1 — PLANNING

*Use this phase in Claude.ai chat or Claude Code before any implementation.*  
*Goal: produce a reviewed plan before touching the codebase.*

### Planning Instructions

You are planning — not implementing. Produce a written plan only.

**Step 1: Summarize the component**
In your own words (3-5 sentences), explain what the MCP servers do, why they exist as a separate layer, and what depends on them. If anything in the spec is unclear, ask now.

**Step 2: Identify the build order**
List the files you will create, in the exact order you will create them. Justify the order. The shared layer must come before any server.

Suggested order to validate:
```
1. mcp-servers/shared/models.py         (shared Pydantic models — everything depends on this)
2. mcp-servers/shared/cache.py          (cache helpers — all servers use this)
3. mcp-servers/ballot_data/sources/     (external API clients — needed by tools)
4. mcp-servers/ballot_data/tools.py     (tool handlers)
5. mcp-servers/ballot_data/server.py    (MCP server entry point)
6. mcp-servers/legislation/parsers/     (deterministic parsers)
7. mcp-servers/legislation/tools.py
8. mcp-servers/legislation/server.py
9. mcp-servers/news/bias_ratings.json   (static data — seed before writing tools)
10. mcp-servers/news/tools.py
11. mcp-servers/news/server.py
12. tests/mcp_servers/conftest.py
13. tests/mcp_servers/test_*.py         (one file per server)
```

**Step 3: List dependencies and risks**
For each external dependency (Google Civic API, Ballotpedia, NewsAPI, OpenSecrets), answer:
- What happens if this API is unavailable during development?
- What mock/stub will you use in tests?
- What is the fallback behavior at runtime?

**Step 4: Confirm constraints**
List the 5 most important constraints from `spec-mcp-servers.md` section 10. For each one, describe exactly how you will enforce it in code (not just "I will follow it").

**Step 5: Flag ambiguities**
List any questions or ambiguities in the spec that could affect implementation. Do not assume answers — ask explicitly.

### ✋ STOP HERE
Do not proceed to Phase 2 until the plan is reviewed and approved.

---

## PHASE 2 — BUILD

*Use this phase in Claude Code (VS Code) after plan approval.*  
*Execute tasks in order. Do not skip ahead. Do not combine tasks.*

---

### Session A: Shared Layer

**Goal:** Create the foundation that all three servers depend on.  
**Complete this session fully before starting Session B.**

#### Task A1: Shared Pydantic Models

Create `mcp-servers/shared/models.py`.

Must contain exactly these models (names must match exactly — other components import them by name):
- `DataSource`
- `DataCompleteness` (Enum: FULL, PARTIAL, LIMITED)
- `ToolError`
- `ElectionSummary`
- `PrecinctInfo`
- `RaceSummary`
- `MeasureSummary` (ballot-level summary, not the full detail model)
- `MeasureDetail`
- `CandidatePosition`
- `CandidateDetail`
- `CampaignFinanceSummary`
- `DonorSummary`
- `IndustryDonation`
- `BallotResponse`
- `MeasureText`
- `MeasureSection`
- `ParsedMeasureText`
- `NewsArticle`
- `NewsSearchResult`
- `SourceBiasRating`

All schemas are defined in `docs/specs/spec-mcp-servers.md` section 3-5.

**Acceptance check before moving on:**
```python
# This must run without errors:
from mcp_servers.shared.models import (
    DataSource, DataCompleteness, ToolError, BallotResponse,
    MeasureDetail, CandidateDetail, NewsSearchResult
)
print("Models OK")
```

**Do not:** Add any models not listed above. Do not add helper methods to models yet. Keep this file purely declarative.

---

#### Task A2: Cache Helpers

Create `mcp-servers/shared/cache.py`.

Must implement exactly these functions (signatures must match):

```python
def get_cached(cache_key: str, db_path: str) -> dict | None:
    """
    Returns cached data as dict if exists and not expired.
    Returns None if not found or expired.
    """

def set_cached(cache_key: str, data: dict, ttl_seconds: int, source: str, db_path: str) -> None:
    """
    Stores data in api_cache table with expiry.
    Overwrites existing entry if cache_key exists.
    """

def is_expired(expires_at: str) -> bool:
    """
    Returns True if expires_at (ISO 8601 string) is in the past.
    """

def make_cache_key(prefix: str, *parts: str) -> str:
    """
    Creates a namespaced, normalized cache key.
    Example: make_cache_key("ballot", "33101", "FL-2026-GEN")
             -> "ballot:33101:FL-2026-GEN"
    Lowercases and strips whitespace from all parts.
    """
```

**Acceptance check:**
```python
# This must pass:
key = make_cache_key("ballot", "  33101  ", "FL-2026-GEN")
assert key == "ballot:33101:fl-2026-gen"

expired = is_expired("2020-01-01T00:00:00Z")
assert expired == True

not_expired = is_expired("2099-01-01T00:00:00Z")
assert not_expired == False
```

**Do not:** Use any ORM. Use raw SQLite via `sqlite3` stdlib module only.

---

#### Task A3: Session A Tests

Create `tests/mcp_servers/test_shared_models.py`.

Write tests for:
1. `DataCompleteness` enum — all three values instantiate correctly
2. `ToolError` — validates `error_code` is SCREAMING_SNAKE_CASE
3. `BallotResponse` — rejects instance missing required `sources` field
4. `make_cache_key` — normalizes whitespace and case
5. `is_expired` — past date returns True, future date returns False
6. `get_cached` / `set_cached` — round-trip test using an in-memory SQLite db

Run tests. All must pass before proceeding to Session B.

```bash
pytest tests/mcp_servers/test_shared_models.py -v
```

---

### Session B: `ballot-data-mcp`

**Goal:** Implement the most important server — address resolution, measure detail, candidate detail, campaign finance.  
**Depends on:** Session A complete and tests passing.

#### Task B1: External API Clients

Create these files with the following responsibilities:

**`mcp-servers/ballot_data/sources/civic.py`**
- Function: `fetch_ballot(address: str, api_key: str) -> dict`
- Calls Google Civic Information API `/voterinfo` endpoint
- Returns raw API response as dict
- Raises no exceptions — returns `{"error": "..."}` on failure
- Validates address is in Florida before calling API (check state in geocoded result)

**`mcp-servers/ballot_data/sources/ballotpedia.py`**
- Function: `fetch_measure(measure_id: str) -> dict`
- Function: `fetch_candidate(candidate_id: str) -> dict`
- Uses Ballotpedia API or scraping (whichever is available for the account)
- Returns raw data as dict, `{"error": "..."}` on failure

**`mcp-servers/ballot_data/sources/fl_elections.py`**
- Function: `fetch_candidate_filing(candidate_id: str) -> dict`
- Calls FL Division of Elections data export
- Returns raw data as dict, `{"error": "..."}` on failure

**`mcp-servers/ballot_data/sources/opensecrets.py`**
- Function: `fetch_candidate_finance(candidate_id: str, api_key: str) -> dict`
- Calls OpenSecrets API
- Returns raw data as dict, `{"error": "..."}` on failure

**Critical rule for all source files:**
Every function must check for `MOCK_EXTERNAL_APIS=true` environment variable. If set, return fixture data from `tests/fixtures/` instead of making real API calls. This is how tests stay offline.

---

#### Task B2: Tool Handlers

Create `mcp-servers/ballot_data/tools.py`.

Implement these functions — one per tool defined in the spec:

```python
async def handle_get_ballot_by_address(
    input: GetBallotByAddressInput,
    db_path: str
) -> BallotResponse | ToolError:
    ...

async def handle_get_measure_detail(
    input: GetMeasureDetailInput,
    db_path: str
) -> MeasureDetail | ToolError:
    ...

async def handle_get_candidate_detail(
    input: GetCandidateDetailInput,
    db_path: str
) -> CandidateDetail | ToolError:
    ...

async def handle_get_campaign_finance(
    input: GetCampaignFinanceInput,
    db_path: str
) -> CampaignFinanceSummary | ToolError:
    ...
```

**Each handler must follow this exact pattern:**
```
1. Validate Florida scope → return OUT_OF_SCOPE ToolError if not FL
2. Check cache → return cached result if valid (set cache_hit: true)
3. Call primary source → if error, try fallback source
4. If all sources fail → return ToolError (recoverable based on error type)
5. Map raw data to Pydantic output model
6. Write to cache
7. Return Pydantic model
```

Do not skip any step. Do not reorder steps.

---

#### Task B3: MCP Server Entry Point

Create `mcp-servers/ballot_data/server.py`.

Register all four tools with the MCP server. Use the `mcp` Python SDK.

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("ballot-data-mcp")

# Register tools here
# Tool names must match exactly: 
#   "get_ballot_by_address"
#   "get_measure_detail" 
#   "get_candidate_detail"
#   "get_campaign_finance"
```

---

#### Task B4: Test Fixtures

Create `tests/fixtures/` with mock API responses:
- `civic_response_33101.json` — sample Google Civic response for Miami zip
- `ballotpedia_measure_fl2022_a2.json` — Amendment 2 from FL 2022
- `ballotpedia_candidate_sample.json` — sample candidate profile
- `opensecrets_finance_sample.json` — sample campaign finance response

These fixtures must match the actual API response shape (check API docs or use real API once to capture a real response, then use as fixture forever).

---

#### Task B5: Session B Tests

Create `tests/mcp_servers/test_ballot_data.py`.

Required test cases (write all before running any):
```
test_get_ballot_by_address_cache_hit
test_get_ballot_by_address_cache_miss_calls_api
test_get_ballot_by_address_non_florida_returns_out_of_state
test_get_ballot_by_address_zip_only_resolves
test_get_ballot_by_address_civic_api_down_uses_fallback
test_get_measure_detail_returns_full_completeness
test_get_measure_detail_missing_fiscal_returns_partial
test_get_measure_detail_historical_fl2022_from_seed
test_get_candidate_detail_positions_mapped_to_taxonomy
test_get_candidate_detail_unknown_id_returns_not_found
test_get_campaign_finance_top_donors_max_five
test_all_responses_have_sources_field
test_all_error_responses_are_tool_error_instances
```

Run: `pytest tests/mcp_servers/test_ballot_data.py -v`  
All must pass. Fix failures before proceeding to Session C.

---

### Session C: `legislation-mcp`

**Goal:** Implement legal text fetching and deterministic parsing.  
**Depends on:** Session A complete.

#### Task C1: Parsers

**`mcp-servers/legislation/parsers/pdf_parser.py`**
- Function: `extract_text_from_pdf(pdf_path: str) -> str`
- Uses `pdfplumber` library
- Returns full text as string
- Returns empty string (not exception) if extraction fails

**`mcp-servers/legislation/parsers/html_parser.py`**
- Function: `extract_measure_text_from_html(html: str) -> str`
- Uses `beautifulsoup4` library
- Targets FL Legislature page structure (find the main content div)
- Returns cleaned text (no HTML tags, no nav/header/footer content)

---

#### Task C2: Tool Handlers

Create `mcp-servers/legislation/tools.py`.

```python
async def handle_get_measure_text(
    input: GetMeasureTextInput,
    db_path: str
) -> MeasureText | ToolError:
    ...

async def handle_parse_measure_text(
    input: ParseMeasureTextInput,
    db_path: str
) -> ParsedMeasureText | ToolError:
    ...
```

**`handle_parse_measure_text` rules:**
- Zero LLM calls. Zero external API calls. Pure Python logic only.
- Section detection priority: numbered sections > ALL-CAPS headings > "BE IT ENACTED" marker > "FISCAL IMPACT" marker > "EFFECTIVE DATE" marker
- Unrecognized content → label as "other"
- Must produce at least 1 section for any non-empty input

---

#### Task C3: Session C Tests

Create `tests/mcp_servers/test_legislation.py`.

Required test cases:
```
test_parse_measure_text_produces_provisions_section
test_parse_measure_text_produces_fiscal_impact_section
test_parse_measure_text_no_llm_calls (mock all LLM clients, assert not called)
test_parse_measure_text_empty_input_returns_tool_error
test_parse_measure_text_unrecognized_content_labeled_other
test_get_measure_text_cache_hit
test_get_measure_text_pdf_fallback_when_html_fails
test_pdf_parser_returns_empty_string_on_corrupt_file (not exception)
```

---

### Session D: `news-mcp`

**Goal:** News search and source bias lookup.  
**Depends on:** Session A complete.

#### Task D1: Seed Bias Ratings

Create `mcp-servers/news/bias_ratings.json`.

Seed with at least these Florida-relevant domains (use AllSides public ratings):
```json
{
  "miamiherald.com": {"rating": "Center", "source": "AllSides"},
  "tampabay.com": {"rating": "Center", "source": "AllSides"},
  "orlandosentinel.com": {"rating": "Center", "source": "AllSides"},
  "sun-sentinel.com": {"rating": "Center", "source": "AllSides"},
  "foxnews.com": {"rating": "Right", "source": "AllSides"},
  "cnn.com": {"rating": "Left", "source": "AllSides"},
  "msnbc.com": {"rating": "Left", "source": "AllSides"},
  "wsj.com": {"rating": "Lean Right", "source": "AllSides"},
  "apnews.com": {"rating": "Center", "source": "AllSides"},
  "reuters.com": {"rating": "Center", "source": "AllSides"},
  "politico.com": {"rating": "Lean Left", "source": "AllSides"},
  "thehill.com": {"rating": "Center", "source": "AllSides"},
  "floridapolitics.com": {"rating": "Center", "source": "AllSides"},
  "flsenate.gov": {"rating": null, "source": null},
  "dos.myflorida.com": {"rating": null, "source": null}
}
```

Add any additional Florida outlets you find with known ratings.

---

#### Task D2: Tool Handlers

Create `mcp-servers/news/tools.py`.

```python
async def handle_search_news(
    input: SearchNewsInput,
    db_path: str
) -> NewsSearchResult | ToolError:
    ...

def handle_get_source_bias(
    input: GetSourceBiasInput
) -> SourceBiasRating:
    # Note: sync not async — reads local file only, no I/O
    ...
```

`handle_get_source_bias` must never return a `ToolError` — unknown domains return `found: false`.

---

#### Task D3: Session D Tests

Create `tests/mcp_servers/test_news.py`.

Required test cases:
```
test_search_news_returns_articles_with_bias_ratings
test_search_news_cache_hit
test_search_news_newsapi_rate_limit_returns_recoverable_error
test_get_source_bias_known_domain_returns_rating
test_get_source_bias_unknown_domain_returns_not_found (not error)
test_get_source_bias_never_raises_exception
test_articles_description_max_300_chars
```

---

## Final Verification

After all four sessions are complete, run the full test suite:

```bash
pytest tests/mcp_servers/ -v --tb=short
```

Expected: all tests pass, zero failures, zero errors.

Then run the Definition of Done checklist from `docs/specs/spec-mcp-servers.md` section 8. Check every item. Do not mark this component complete until every box is checked.

---

## If You Get Stuck

**"I don't know the exact API response format"**
→ Use the mock/fixture pattern. Create a plausible fixture matching the documented API schema. Flag for human to validate with real API call.

**"The spec says X but doing X causes problem Y"**
→ Do not work around it silently. Stop, describe the conflict, propose two options, wait for decision.

**"I'm not sure if this belongs in models.py or in the tool file"**
→ If more than one file will need it → `models.py`. If only one file needs it → define it locally and add a TODO to extract if needed.

**"Tests are failing and I can't figure out why"**
→ Add `print()` statements to isolate. Do not rewrite the test to make it pass. The test is correct — find why the code is wrong.

**"The context is getting long and I'm losing track"**
→ Stop. Summarize: "Here is what I've built so far, here is what remains, here are the open questions." Then continue.
