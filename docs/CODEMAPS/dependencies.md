<!-- Generated: 2026-04-20 | Files scanned: 10 | Token estimate: ~600 -->

# External Dependencies

## MCP Servers & Tools

| Server | Tool | Input | Output | Cache TTL | External API |
|--------|------|-------|--------|-----------|-------------|
| ballot_data | get_ballot_by_address | address, election_id? | BallotResponse | 6h | Google Civic API |
| ballot_data | get_measure_detail | measure_id | MeasureDetail | 12h | SQLite + Ballotpedia |
| ballot_data | get_candidate_detail | candidate_id, topics? | CandidateDetail | 6h | SQLite + Ballotpedia |
| ballot_data | get_campaign_finance | entity_id, entity_type | CampaignFinanceSummary | 24h | OpenFEC / FL DoE |
| legislation | get_measure_text | measure_id, state | MeasureText | 7d | FL Legislature HTML |
| legislation | parse_measure_text | measure_id, raw_text | ParsedMeasureText | none | Pure function |
| news | search_news | query, dates, max | NewsSearchResult | 1h | NewsAPI |
| news | get_source_bias | domain | SourceBiasRating | none | bias_ratings.json |

## External APIs

| API | Env Var | Used By | Purpose |
|-----|---------|---------|---------|
| Google Gemini | GEMINI_API_KEY, GEMINI_MODEL | llm_client.py | AI reasoning (temp=0.1, gemini-2.5-flash) |
| Anthropic Claude | ANTHROPIC_API_KEY | (deprecated — removed in Slice 3) | legacy, still required by config |
| Google Civic | GOOGLE_CIVIC_API_KEY | sources/civic.py | Voter info, ballot lookup |
| NewsAPI | NEWSAPI_KEY | sources/newsapi.py | News article search |
| OpenFEC | OPENFEC_API_KEY | sources/openfec.py | Federal campaign finance |
| FL DoE Finance | (public) | sources/fl_finance.py | State/local campaign finance |
| FL Legislature | (public) | legislation/measure_text.py | Legal text HTML |
| Ballotpedia | (public, scrape) | sources/ballotpedia.py | Measure/candidate profiles |

## Python Dependencies (requirements.txt)

| Package | Version | Layer |
|---------|---------|-------|
| fastapi | ~=0.128.0 | API framework |
| uvicorn[standard] | ~=0.30.0 | ASGI server |
| slowapi | ~=0.1.9 | Rate limiting |
| aiosqlite | ~=0.20.0 | Async SQLite |
| pydantic | ~=2.9.0 | Data validation |
| pydantic-settings | ~=2.6.0 | Env var config |
| httpx | ~=0.28.0 | HTTP client |
| google-genai | ~=1.73.1 | Gemini SDK (primary LLM) |
| anthropic | ~=0.84.0 | Claude SDK (legacy — removed Slice 3) |
| mcp | ~=1.0.0 | MCP protocol |
| pdfplumber | ~=0.11.0 | PDF text extraction |
| pytest | ~=8.2.0 | Testing |
| pytest-asyncio | ~=0.24.0 | Async test support |

## Node Dependencies (apps/web/package.json)

| Package | Version | Purpose |
|---------|---------|---------|
| next | 16.1.6 | React framework |
| react | 19.2.3 | UI library |
| react-dom | 19.2.3 | DOM renderer |
| tailwindcss | 4 | Utility CSS |
| typescript | 5 | Type safety |
| jest | 30.2.0 | Test runner |
| @testing-library/react | 16.3.2 | Component testing |

## Mock Flags

Master: `MOCK_EXTERNAL_APIS=true` overrides all per-source flags.

Per-source: MOCK_CIVIC_API, MOCK_OPENFEC_API, MOCK_FL_FINANCE_API, MOCK_BALLOTPEDIA_API, MOCK_FL_ELECTIONS_API, MOCK_NEWSAPI, MOCK_LEGISLATION_API

LLM mock: `MOCK_LLM=true` bypasses Gemini API (loads tests/fixtures/llm/mock_response.json). `MOCK_CLAUDE` is retained until Slice 3 but no longer consulted by llm_client.py.
