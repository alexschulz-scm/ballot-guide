# Ballot Guide — Gap Analysis: Design Documents vs Implementation

> Updated: 2026-03-05 — evaluated against deployed MVP + recent follow-up and report enhancements.

This document compares the three design documents (`neutrality-contract.md`, `user-flows.md`, `vision.md`) against what is actually built and deployed.

---

## neutrality-contract.md

| Contract Requirement | Status | Notes |
|---|---|---|
| Output schemas have no recommendation fields | Implemented | Pydantic models enforce this structurally |
| `proponent_argument` + `opponent_argument` both required | Implemented | Required fields in measure schemas |
| `sources` required list (min length 1) | Implemented | Enforced in schemas |
| `relevance_to_priorities` describes connection only | Implemented | Prompt + schema constraints |
| Verbatim neutrality prompt block in system prompt | Implemented | `apps/api/orchestrator/prompts/system.txt` has the block (slightly reworded, same rules) |
| 10% audit sampling of generated summaries | **Not implemented** | No audit log table or mechanism exists |
| Source bias labeling (AllSides/Ad Fontes) | Implemented | `BiasLabel` component in `SourceList.tsx` displays rating + source name with optional link to rating page |
| Recommendation refusal flow | Implemented | Handled in system prompt + follow-up stage |

### Gap: Audit Sampling

The neutrality contract specifies a 10% random sampling of generated summaries logged for manual review with a 5-point checklist. This was never added to any build spec or session, so it was never built. For MVP this is acceptable — it's a quality assurance process, not a user-facing feature. Worth adding post-MVP as traffic grows.

---

## user-flows.md

### User Flows

| Flow | Status | Details |
|---|---|---|
| **Flow 1: First-time session** | Implemented | Chat -> address -> priorities -> streaming -> conversational summary -> report view. All steps work end-to-end. |
| **Flow 2: Deep dive on specific item** | Implemented | Follow-up stage (`apps/api/orchestrator/stages/follow_up.py`) detects user intent and fetches live data from MCP servers: legal text via `handle_get_measure_text()`, campaign finance via `handle_get_campaign_finance()`, news via `handle_search_news()`. Returns deeper answers with source attribution. |
| **Flow 3: Candidate comparison** | Implemented | `ComparisonTable.tsx` renders candidates as columns and priority topics as rows. Desktop table layout, mobile stacked cards. Shown via toggle button in `RaceCard`. Returns null if fewer than 2 candidates. |
| **Flow 4: Quick lookup (election day)** | Partial | Returning session detection works. Shows "Welcome back" + "View Report" button. But there's no "accelerated/quick summary" mode — it shows the existing full report. |
| **Flow 5: Explainer mode** | Partial | Follow-up mode can answer civics questions conversationally, but there's no explicit "bridge back to ballot" logic. It works but isn't specialized for civics explainers. |
| **Flow 6: Report export & sharing** | Implemented | Print CSS with `.no-print` classes. "Share" button in `ReportHeader.tsx` copies URL to clipboard with "Link copied" feedback. `SharedDisclaimer` component renders on shared links, showing original user's priorities with "Create your own" CTA. |

### Feature Matrix (from user-flows.md)

| Feature | Described | Built |
|---|---|---|
| Address resolution | Yes | Yes (via Google Civic / mock) |
| Priority collection (chips + free text) | Yes | Yes (`PriorityChips.tsx` + free text input) |
| Ballot lookup | Yes | Yes |
| Measure summary | Yes | Yes |
| Measure full text (on-demand in follow-up) | Yes | Yes — follow-up detects legal text intent and calls `handle_get_measure_text()` |
| Candidate profile | Yes | Yes |
| Candidate comparison (side-by-side) | Yes | Yes — `ComparisonTable.tsx` with responsive layout |
| Campaign finance (on-demand in follow-up) | Yes | Yes — follow-up detects finance intent and calls `handle_get_campaign_finance()` |
| News coverage (on-demand in follow-up) | Yes | Yes — follow-up detects news intent and calls `handle_search_news()` |
| Civics explainer | Yes | Partial (conversational, not specialized) |
| Relevance ranking | Yes | Yes |
| Report view | Yes | Yes |
| Export / share | Yes | Yes — print + copy-link with shared disclaimer |
| Returning session | Yes | Yes |

### Decisions (from user-flows.md)

| Decision | Status | Notes |
|---|---|---|
| 1. Priority chips (hybrid model) | Implemented | 10 chips matching the topic taxonomy, plus free text |
| 2. Session persistence / staleness check | Implemented | `check_data_freshness()` in store returns `fresh`/`stale`/`very_stale`. `StalenessBar.tsx` renders blue (stale) or yellow (very stale) banners with refresh button. All text via i18n. |
| 3. Multi-person households | Partial | `display_name` field wired end-to-end (intake -> store -> API response -> frontend types) but no explicit "What should I call you?" prompt or multi-person household UI messaging |
| 4. Local races limited data state | Implemented | `LimitedDataCard.tsx` component exists |
| 5. Language support architecture | Implemented | i18n system with `t()`, `en.json`. No Spanish locale yet (as planned for v2). |

### Edge Cases (from user-flows.md)

| Edge Case | Status | Notes |
|---|---|---|
| Address not found | Implemented | Intake stage handles via prompt |
| Address outside Florida | Implemented | Rejected at intake per CLAUDE.md rules |
| Election not yet finalized | **Not implemented** | No explicit "not finalized" or "still filing" messaging in UI or orchestrator |
| Data unavailable for a race | Implemented | `LimitedDataCard.tsx` handles this |
| User asks for a recommendation | Implemented | System prompt rule #6 + follow-up prompt |
| User expresses strong political opinion | Implemented | Handled by neutrality rules in system prompt |

---

## vision.md

| Vision Element | Status | Notes |
|---|---|---|
| Conversational AI that understands priorities + ballot | Implemented | Core flow works end-to-end |
| Structured, printable report | Implemented | Report page with print CSS |
| Factual, source-cited reference | Implemented | Sources on every item, bias labels displayed |
| Proponent + opponent with equal rigor | Implemented | Structural enforcement via schemas |
| Never tells users who to vote for | Implemented | Schema + prompt enforcement |
| Does not infer political alignment | Implemented | Prompt rule #6 |
| Florida 2026 General + 2022 historical | Implemented | Plus FL-2024-GEN as bonus |
| Web chat + structured ballot report | Implemented | Both interfaces built |
| Azure Container Apps (scale to zero) | Implemented | Deployed with `minReplicas: 0` |
| Full guide in < 60 seconds | **Untested** | All external APIs currently mocked; real Claude latency unknown |

---

## Summary

### Fully Implemented (core vision delivered)

- Personalized, neutral, source-cited ballot guides
- Conversational intake with priority chips + free text
- 5-stage orchestrator pipeline (intake -> ballot -> analysis -> ranking -> report)
- Follow-up stage with live MCP data fetching (legal text, finance, news)
- Candidate comparison table (responsive, topic-by-topic)
- Structured report view with print support
- Shareable report links with copy-to-clipboard and shared disclaimer
- Source bias labels (AllSides/Ad Fontes) displayed in report UI
- Data staleness detection with visual banners and refresh
- Neutrality enforcement (schema + prompt + display rules)
- Scale-to-zero Azure deployment with auto-seed
- Returning session detection
- i18n architecture (English MVP, ready for Spanish)
- 3 MCP servers with 8 tools + caching
- 41 test files (13 frontend + 28 backend)

### Gaps (post-MVP priorities)

| Gap | Source Document | Effort | Priority |
|---|---|---|---|
| Audit sampling (10% of summaries) | neutrality-contract.md | Small | Medium — quality assurance |
| Quick summary mode (election day) | user-flows.md, Flow 4 | Small | Low — existing report serves the purpose |
| Election not finalized messaging | user-flows.md, Edge Cases | Small | Low — only relevant pre-ballot-finalization |
| Multi-person households (explicit UI) | user-flows.md, Decision 3 | Small | Low — `display_name` plumbed but no UI prompt |
| Civics explainer (bridge back to ballot) | user-flows.md, Flow 5 | Small | Low — works conversationally already |
| End-to-end latency test with real APIs | vision.md | N/A | High — must verify < 60s promise |
