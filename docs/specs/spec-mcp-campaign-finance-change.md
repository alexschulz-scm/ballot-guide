# Spec Change: Campaign Finance Source Migration

**Type:** Breaking change — external API replacement  
**Affects:** `spec-mcp-servers.md` Section 3.4 only  
**Reason:** OpenSecrets API discontinued April 15, 2025  
**Status:** Ready to implement — existing code is `opensecrets.py` which must be replaced  
**Date:** 2026-03-03

---

## Summary of Changes

| Item | Before | After |
|------|--------|-------|
| Federal races source | OpenSecrets REST API | OpenFEC REST API (api.open.fec.gov) |
| State/local races source | FL EFIS (implied) | FL Division of Elections bulk CSV |
| Source file | `sources/opensecrets.py` | `sources/openfec.py` + `sources/fl_finance.py` |
| Env var | `OPENSECRETS_API_KEY` | `OPENFEC_API_KEY` |
| Mock response shape | Unchanged | Unchanged |
| Output schema | Unchanged | Unchanged |
| Cache key | Unchanged | Unchanged |

The `CampaignFinanceSummary`, `DonorSummary`, and `IndustryDonation` output schemas
are unchanged. The agent orchestrator and frontend are unaffected.

---

## Section 3.4 — Full Replacement Text

Replace Section 3.4 of `spec-mcp-servers.md` entirely with the following:

---

### 3.4 Tool: `get_campaign_finance`

Returns campaign finance summary for a candidate or measure campaign.

**Input schema:** *(unchanged)*
```python
class GetCampaignFinanceInput(BaseModel):
    entity_id: str           # candidate_id or measure_id
    entity_type: str         # "candidate" | "measure"
```

**Output schema:** *(unchanged)*
```python
class CampaignFinanceSummary(BaseModel):
    entity_id: str
    entity_type: str
    total_raised: float | None
    total_spent: float | None
    top_donors: list[DonorSummary]        # top 5 max
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

**Error codes:**
| Code | Recoverable | Meaning |
|------|-------------|---------|
| `FINANCE_UNAVAILABLE` | true | All sources failed or returned errors |
| `RATE_LIMITED` | true | API quota exceeded — retry after backoff |
| `ENTITY_NOT_FOUND` | false | No finance data found for this entity in any source |

**Data sources (in priority order):**

The tool routes to a different source depending on race type:

```
Federal races (US Senate, US House, US President):
  1. SQLite cache
  2. OpenFEC API  (api.open.fec.gov)
  3. Return FINANCE_UNAVAILABLE if both fail

State/local races (FL Governor, FL Legislature, FL Constitutional Officers, local):
  1. SQLite cache
  2. FL Division of Elections bulk CSV download
  3. Return FINANCE_UNAVAILABLE if both fail
```

**Race type detection:**  
The tool infers race type from `entity_id` prefix convention:
- `fed-*` → federal → OpenFEC
- `fl-*` or `local-*` → state/local → FL Division of Elections
- Unknown prefix → attempt OpenFEC first, then FL DoE fallback

**Cache TTL:** 24 hours  
**Cache key:** `finance:{entity_id}` *(unchanged)*

---

### 3.4.1 OpenFEC API Client (`sources/openfec.py`)

Replaces `sources/opensecrets.py`. Delete `opensecrets.py` — do not keep it.

**Base URL:** `https://api.open.fec.gov/v1/`  
**Auth:** API key via `?api_key=` query param (free key at api.data.gov)  
**Env var:** `OPENFEC_API_KEY`

**Endpoints used:**

| Data needed | Endpoint |
|-------------|----------|
| Find candidate by name/state | `GET /candidates/` |
| Total raised + spent | `GET /candidates/{candidate_id}/totals/` |
| Top donors (individual contributions) | `GET /schedules/schedule_a/` |

**Mapping to `CampaignFinanceSummary`:**

```python
# From /candidates/{id}/totals/
total_raised  = response["results"][0]["receipts"]
total_spent   = response["results"][0]["disbursements"]
reporting_period = str(response["results"][0]["cycle"])  # e.g. "2024"

# From /schedules/schedule_a/ (sorted by contribution_receipt_amount desc, top 5)
top_donors = [
    DonorSummary(
        name=item["contributor_name"],
        amount=item["contribution_receipt_amount"],
        category=_map_entity_type(item["entity_type"]),  # see below
    )
    for item in response["results"][:5]
]

# entity_type mapping
def _map_entity_type(fec_type: str) -> str | None:
    return {
        "IND": "individual",
        "PAC": "PAC",
        "CCM": "PAC",
        "ORG": "corporation",
        "PTY": "PAC",
        "COM": "PAC",
    }.get(fec_type)

# industry_breakdown: OpenFEC does not provide industry breakdown natively.
# Set to empty list []. Do not attempt to derive it.
industry_breakdown = []

# SourceCitation
sources = [SourceCitation(
    name="Federal Election Commission",
    url=f"https://www.fec.gov/data/candidate/{fec_candidate_id}/",
    fetched_at=datetime.now(timezone.utc).isoformat(),
    bias_rating=None,
)]
```

**Rate limits:** 1,000 requests/hour with API key. Cache aggressively — this is the binding constraint.

**Mock response:** Keep the same shape as the existing `MOCK_OPENSECRETS_RESPONSE` in
`opensecrets.py`. The mock data structure is correct; only the source name changes:

```python
MOCK_OPENFEC_RESPONSE: dict = {
    "entity_id": "mock_entity",
    "entity_type": "candidate",
    "total_raised": 218000000.0,
    "total_spent": 185000000.0,
    "top_donors": [
        {"name": "Florida GOP", "amount": 5000000.0, "category": "PAC"},
        {"name": "Ken Griffin", "amount": 5000000.0, "category": "individual"},
        {"name": "Steve Schwarzman", "amount": 2500000.0, "category": "individual"},
    ],
    "industry_breakdown": [],
    "reporting_period": "2024",
}
```

---

### 3.4.2 FL Division of Elections Finance Client (`sources/fl_finance.py`)

Handles state and local race finance data.

**Source:** Florida Division of Elections campaign finance bulk data  
**URL pattern:** `https://dos.elections.myflorida.com/campaign-finance/contributions/`  
**Access method:** Bulk CSV download (no REST API available)

**Strategy:**
1. Download the relevant election-cycle CSV for the candidate's race
2. Parse and filter rows matching `entity_id`
3. Aggregate: sum contributions for `total_raised`, sum expenditures for `total_spent`
4. Extract top 5 contributors by amount for `top_donors`
5. Cache the parsed result for 24 hours

**Mapping to `CampaignFinanceSummary`:**

```python
# Aggregate from contribution rows
total_raised = sum(row["amount"] for row in contributions)
total_spent  = sum(row["amount"] for row in expenditures)

top_donors = [
    DonorSummary(
        name=row["contributor_name"],
        amount=row["amount"],
        category=None,   # FL DoE CSV does not classify donor type
    )
    for row in sorted(contributions, key=lambda r: r["amount"], reverse=True)[:5]
]

industry_breakdown = []   # Not available in FL DoE data

reporting_period = f"{election_year}"

sources = [SourceCitation(
    name="Florida Division of Elections",
    url="https://dos.elections.myflorida.com/campaign-finance/contributions/",
    fetched_at=datetime.now(timezone.utc).isoformat(),
    bias_rating=None,
)]
```

**data_completeness logic:**
- `FULL` if both `total_raised` and at least one donor in `top_donors`
- `PARTIAL` if `total_raised` is populated but `top_donors` is empty
- `LIMITED` if no finance data found at all (return `ENTITY_NOT_FOUND` error instead)

---

## File Structure Change

Update Section 6 file structure. Replace `opensecrets.py` with two new files:

```
ballot_data/
└── sources/
    ├── __init__.py
    ├── civic.py          # unchanged
    ├── ballotpedia.py    # unchanged
    ├── fl_elections.py   # unchanged
    ├── openfec.py        # NEW — replaces opensecrets.py
    └── fl_finance.py     # NEW — FL Division of Elections finance
```

**Delete:** `sources/opensecrets.py`

---

## Environment Variable Change

**Remove:** `OPENSECRETS_API_KEY`  
**Add:** `OPENFEC_API_KEY`

Update in:
- `.env.example`
- `ROADMAP.md` Appendix A
- `apps/api/config.py` (remove old, add new)
- Any CI/CD secrets config

Registration at: https://api.data.gov/signup/ — free, instant, no approval required.

---

## Acceptance Criteria Changes

Replace the existing campaign finance acceptance criterion (none existed explicitly)
with these two new ones. Append to Section 7:

- [ ] **AC-MCP-18:** `get_campaign_finance` with a `fed-*` entity_id calls OpenFEC API
  (`api.open.fec.gov`), not any OpenSecrets domain — verified by checking HTTP call log
- [ ] **AC-MCP-19:** `get_campaign_finance` with a `fl-*` entity_id calls FL Division of
  Elections CSV endpoint, not OpenFEC — verified by checking HTTP call log
- [ ] **AC-MCP-20:** With `MOCK_EXTERNAL_APIS=true`, `get_campaign_finance` returns valid
  `CampaignFinanceSummary` with `data_completeness: "full"` and zero HTTP calls made

---

## Definition of Done Additions

Append to Section 8:

- [ ] `sources/opensecrets.py` has been deleted from the repository
- [ ] `OPENSECRETS_API_KEY` does not appear in any source file, config, or `.env.example`
- [ ] `OPENFEC_API_KEY` is present in `.env.example` with a comment linking to api.data.gov/signup
- [ ] OpenFEC and FL finance clients both tested with error injection (404, 429, 503, malformed CSV)

---

## Implementation Notes for the Agent

**Do not rewrite the tool handler** (`get_campaign_finance` in `tools.py`). The handler
calls `fetch_finance_for_entity(entity_id, entity_type, api_key)` — keep that interface.
Only the implementation of that function changes (new source files replace opensecrets.py).

**The routing logic** (federal → OpenFEC, state → FL DoE) belongs in the tool handler,
not inside the individual source clients. Each client should be a pure fetch-and-parse
module with no routing logic.

**OpenFEC candidate ID lookup:** The FEC candidate ID (`P00000001` format) will likely
not match the internal `entity_id` format. The client needs a lookup step:
1. Call `GET /candidates/?q={candidate_name}&state=FL` to find the FEC candidate ID
2. Cache the name→FEC ID mapping separately with a long TTL (7 days)
3. Use the FEC ID for subsequent totals and schedule_a calls

**FL DoE CSV is large.** Download once per election cycle and cache the full CSV, then
filter in memory. Do not re-download the full CSV for each candidate lookup.
