# Ballot Guide — Gap Analysis: Design Documents vs Implementation

> Updated: 2026-03-04 — evaluated against deployed MVP.

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
| Source bias labeling (AllSides/Ad Fontes) | Partial | `get_source_bias` tool exists in the news MCP server, but bias labels aren't prominently surfaced in the report UI |
| Recommendation refusal flow | Implemented | Handled in system prompt + follow-up stage |

### Gap: Audit Sampling

The neutrality contract specifies a 10% random sampling of generated summaries logged for manual review with a 5-point checklist. This was never added to any build spec or session, so it was never built. For MVP this is acceptable — it's a quality assurance process, not a user-facing feature. Worth adding post-MVP as traffic grows.

---

## user-flows.md

### User Flows

| Flow | Status | Details |
|---|---|---|
| **Flow 1: First-time session** | Implemented | Chat → address → priorities → streaming → conversational summary → report view. All steps work end-to-end. |
| **Flow 2: Deep dive on specific item** | Partial | Follow-up mode exists (`apps/api/orchestrator/stages/follow_up.py`) and lets users ask questions after a report. But it answers from the *existing report* only (max 300 words). It does NOT fetch full legal text, campaign finance, or news coverage on demand as described. |
| **Flow 3: Candidate comparison** | **Not implemented** | No comparison mode, no side-by-side rendering, no comparison table component. Not in any build spec. |
| **Flow 4: Quick lookup (election day)** | Partial | Returning session detection works. Shows "Welcome back" + "View Report" button. But there's no "accelerated/quick summary" mode — it shows the existing full report. |
| **Flow 5: Explainer mode** | Partial | Follow-up mode can answer civics questions conversationally, but there's no explicit "bridge back to ballot" logic. It works but isn't specialized for civics explainers. |
| **Flow 6: Report export & sharing** | Partial | Print CSS exists with `.no-print` classes. Browser print-to-PDF works. But there's no "Copy link" / shareable URL for read-only reports, no disclaimer on shared reports. |

### Feature Matrix (from user-flows.md)

| Feature | Described | Built |
|---|---|---|
| Address resolution | Yes | Yes (via Google Civic / mock) |
| Priority collection (chips + free text) | Yes | Yes (`PriorityChips.tsx` + free text input) |
| Ballot lookup | Yes | Yes |
| Measure summary | Yes | Yes |
| Measure full text (on-demand in follow-up) | Yes | **No** — follow-up uses existing report only |
| Candidate profile | Yes | Yes |
| Candidate comparison (side-by-side) | Yes | **No** |
| Campaign finance (on-demand in follow-up) | Yes | **No** — data exists in seed but not fetchable on-demand |
| News coverage (on-demand in follow-up) | Yes | **No** — not fetchable in follow-up mode |
| Civics explainer | Yes | Partial (conversational, not specialized) |
| Relevance ranking | Yes | Yes |
| Report view | Yes | Yes |
| Export / share | Yes | Partial (print only, no shareable link) |
| Returning session | Yes | Yes |

### Decisions (from user-flows.md)

| Decision | Status | Notes |
|---|---|---|
| 1. Priority chips (hybrid model) | Implemented | 10 chips matching the topic taxonomy, plus free text |
| 2. Session persistence / staleness check | Partial | Sessions persist; `StalenessBar.tsx` component exists; `check_data_freshness()` in store but may not be wired end-to-end |
| 3. Multi-person households | **Not implemented** | No `display_name` field used, no "What should I call you?" prompt |
| 4. Local races limited data state | Implemented | `LimitedDataCard.tsx` component exists |
| 5. Language support architecture | Implemented | i18n system with `t()`, `en.json` with 67 keys. No Spanish locale yet (as planned for v2). |

### Edge Cases (from user-flows.md)

| Edge Case | Status | Notes |
|---|---|---|
| Address not found | Implemented | Intake stage handles via prompt |
| Address outside Florida | Implemented | Rejected at intake per CLAUDE.md rules |
| Election not yet finalized | Partial | Seed data exists with placeholder candidates, but no explicit "not finalized" messaging |
| Data unavailable for a race | Implemented | `LimitedDataCard.tsx` handles this |
| User asks for a recommendation | Implemented | System prompt rule #6 + follow-up prompt |
| User expresses strong political opinion | Implemented | Handled by neutrality rules in system prompt |

---

## vision.md

| Vision Element | Status | Notes |
|---|---|---|
| Conversational AI that understands priorities + ballot | Implemented | Core flow works end-to-end |
| Structured, printable report | Implemented | Report page with print CSS |
| Factual, source-cited reference | Implemented | Sources on every item |
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
- 5-stage orchestrator pipeline (intake → ballot → analysis → ranking → report)
- Structured report view with print support
- Neutrality enforcement (schema + prompt + display rules)
- Scale-to-zero Azure deployment with auto-seed
- Follow-up questions on existing reports
- Returning session detection
- i18n architecture (English MVP, ready for Spanish)
- 3 MCP servers with 8 tools + caching
- 143 tests passing (54 frontend + 89 backend)

### Gaps (post-MVP priorities)

| Gap | Source Document | Effort | Priority |
|---|---|---|---|
| Candidate comparison mode (side-by-side) | user-flows.md, Flow 3 | Medium | High — differentiating feature |
| Deep-dive follow-up with live data fetching | user-flows.md, Flow 2 | Medium | High — currently answers from cached report only |
| Shareable report links (copy URL + disclaimer) | user-flows.md, Flow 6 | Small | Medium |
| Audit sampling (10% of summaries) | neutrality-contract.md | Small | Medium — quality assurance |
| Source bias labels in report UI | neutrality-contract.md | Small | Low — data exists, needs UI |
| Quick summary mode (election day) | user-flows.md, Flow 4 | Small | Low — existing report serves the purpose |
| Multi-person households (display_name) | user-flows.md, Decision 3 | Small | Low |
| Civics explainer (bridge back to ballot) | user-flows.md, Flow 5 | Small | Low — works conversationally already |
| End-to-end latency test with real APIs | vision.md | N/A | High — must verify < 60s promise |
