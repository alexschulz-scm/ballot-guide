# Spec: Frontend

**Status:** Draft v1.0  
**Component:** `apps/web/`  
**Depends on:** `spec-api.md`, `user-flows.md`, `neutrality-contract.md`  
**Consumed by:** Users  
**Last updated:** 2026-02-28

---

## 1. Overview

The frontend is a Next.js application with two primary views: a **Chat View** where users converse with the agent and receive streaming progress, and a **Report View** where the completed ballot guide is displayed in a structured, printable format.

The frontend is deliberately simple in structure — two routes, no authentication, no client-side state management library. All persistent state lives server-side in SQLite; the frontend stores only `session_id` in `localStorage` and derives everything else from the API.

**Tech stack:**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- No UI component library — custom components only
- `localStorage` for session ID persistence only
- Native `EventSource` API for SSE consumption

### What the frontend is NOT responsible for
- Generating ballot content (agent does this)
- Storing user data beyond `session_id` in localStorage
- Authentication or accounts (none in MVP)
- Internationalization rendering (i18n architecture supported but English only)
- PDF generation (browser print dialog only)

---

## 2. Routes

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `ChatView` | First-time session and conversation interface |
| `/report/[sessionId]` | `ReportView` | Full ballot guide, printable |

No other routes for MVP. The `/report/[sessionId]` route is also the shareable link destination — it renders identically for the original user and recipients.

---

## 3. Chat View (`/`)

### 3.1 Layout

```
┌─────────────────────────────────────────────┐
│  HEADER: "Ballot Guide" wordmark + tagline   │
├─────────────────────────────────────────────┤
│                                             │
│  MESSAGE THREAD                             │
│  (scrollable, grows upward)                 │
│                                             │
│  [assistant bubble] Welcome message          │
│  [user bubble] I live in 33101...           │
│  [assistant bubble] Found your ballot...    │
│  [progress bar] Analyzing Amendment 1...    │
│  [assistant bubble] Here's what matters...  │
│                                             │
├─────────────────────────────────────────────┤
│  PRIORITY CHIPS (shown once, after address) │
│  [🏠 Housing] [🎓 Education] [💰 Taxes] ... │
├─────────────────────────────────────────────┤
│  INPUT BAR                                  │
│  [text field] [send button]                 │
└─────────────────────────────────────────────┘
```

### 3.2 Initial State (no session)

On first load with no `session_id` in localStorage:
1. Create session via `POST /api/v1/session`
2. Store returned `session_id` in localStorage
3. Show welcome message: "Hi — I'm here to help you understand your Florida ballot. Tell me your zip code or address to get started."
4. Input field focused, placeholder: "Type your zip code or address..."

### 3.3 Returning Session

On load with `session_id` in localStorage:
1. Call `GET /api/v1/session/{id}`
2. If `has_report: true` → show "Welcome back" message with link to report
3. If `has_report: false` → restore message history, pick up where user left off
4. If session not found (404) → clear localStorage, start fresh as new session

### 3.4 Message Thread

Each message is a bubble. Three types:

**User bubble** — right-aligned, user's text verbatim.

**Assistant bubble** — left-aligned. Renders markdown (bold, lists, links). Contains source links when present.

**Progress bubble** — left-aligned, distinct visual treatment. Used during orchestrator processing. Contains:
- A status label that updates as events arrive: "Looking up your ballot..." → "Analyzing Amendment 1 (1/10)..." → "Ranking by your priorities..."
- An animated progress indicator
- Replaced by the final assistant bubble when `report_complete` fires

### 3.5 Priority Chips

Shown **once** after the orchestrator returns `ballot_found` event. Disappear after user selects or types priorities.

10 chips matching the topic taxonomy:
```
🏠 Housing & Rent       🎓 Education & Schools    💰 Taxes & Cost of Living
🏥 Healthcare           🌿 Environment & Climate  🚔 Public Safety & Crime
💼 Jobs & Economy       🗳️ Voting & Elections     🛣️ Infrastructure          
👴 Senior Services
```

**Chip behavior:**
- Tap/click toggles selection (visual highlight)
- Multiple selection allowed
- On "See My Ballot Guide" button press: sends selected chips as a message ("I care about: Housing & Rent, Education & Schools")
- Free text input always available in parallel — user can type instead of or in addition to chips
- Chips are a UX convenience, not a replacement for the text input

### 3.6 SSE Event Handling

The frontend consumes the SSE stream from `POST /api/v1/session/{id}/message`.

```typescript
// Event → UI mapping
"intake_complete"     → update progress bubble: "Got it — looking up your ballot..."
"ballot_found"        → update progress bubble: "Found your ballot! {item_count} items. Analyzing..."
                     → show priority chips if priorities not yet set
"item_analyzed"       → update progress bubble: "Analyzing {item_title} ({items_complete}/{items_total})..."
"ranking_complete"    → update progress bubble: "Almost done — organizing by your priorities..."
"report_complete"     → replace progress bubble with assistant summary message
                     → show "View Full Ballot Guide →" button
"clarification_needed"→ replace progress bubble with assistant question
"error"               → replace progress bubble with error message + retry option
"done"                → dismiss progress bubble if still showing (cleanup)
```

**SSE implementation using native `EventSource`:**

Note: `EventSource` only supports GET requests. Since the message endpoint is a POST, use `fetch` with `ReadableStream` instead:

```typescript
async function streamMessage(sessionId: string, content: string) {
  const response = await fetch(`/api/v1/session/${sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const event = JSON.parse(line.slice(6));
        handleEvent(event);
      }
    }
  }
}
```

### 3.7 "View Full Ballot Guide" Button

Shown in the chat after `report_complete` event. Navigates to `/report/[sessionId]`. Opens in same tab — not a new tab.

---

## 4. Report View (`/report/[sessionId]`)

### 4.1 Layout

```
┌──────────────────────────────────────────────────────┐
│  HEADER                                              │
│  "Your Ballot Guide"  |  "Back to Chat"  "Print"     │
│  Election: 2026 Florida General Election             │
│  Personalized for: Housing, Education                │
│  Generated: March 1, 2026   [Staleness banner?]      │
├──────────────────────────────────────────────────────┤
│  BALLOT ITEM CARDS (ordered by relevance)            │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ 🏠  Amendment 3 — Housing Zoning Reform        │  │
│  │ Relevance: matches your interest in Housing    │  │
│  │                                                │  │
│  │ Summary: [plain English, 150 words max]        │  │
│  │                                                │  │
│  │ If YES passes: [50 words]                      │  │
│  │ If NO wins:    [50 words]                      │  │
│  │                                                │  │
│  │ 💰 Fiscal Impact: [from official source]       │  │
│  │                                                │  │
│  │ ✅ For:    [proponent argument, 100 words]      │  │
│  │ ❌ Against: [opponent argument, 100 words]     │  │
│  │                                                │  │
│  │ Sources: [Ballotpedia] [FL Div of Elections]   │  │
│  │                                    [▼ Details] │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  [more cards...]                                     │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ 🎓  Governor Race                              │  │
│  │ Relevance: candidates differ on education      │  │
│  │                                                │  │
│  │ CANDIDATE A — Party                            │  │
│  │ [bio, 75 words]                                │  │
│  │ On Education: [position, 1 sentence, source]   │  │
│  │ On Housing: [position, 1 sentence, source]     │  │
│  │ Funding: $12M raised. Top donors: [3 names]    │  │
│  │                                                │  │
│  │ CANDIDATE B — Party                            │  │
│  │ [same structure]                               │  │
│  │                                                │  │
│  │ Sources: [Ballotpedia] [OpenSecrets]           │  │
│  └────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│  FOOTER                                              │
│  "Sources and methodology"  "About Ballot Guide"     │
│  [Share link] [Print]                                │
└──────────────────────────────────────────────────────┘
```

### 4.2 Report Card — Measure

Each measure renders as a card with these sections (all always present, in this order):

1. **Header** — short title, relevance tag (topic emoji + "matches your interest in X")
2. **Summary** — `plain_english_summary`, max 150 words, no jargon
3. **What each outcome means** — two short blocks: "If YES passes" and "If NO wins"
4. **Fiscal Impact** — from official source, with source link. If null: "Fiscal impact not yet published."
5. **For / Against** — two equal sections, `proponent_argument` and `opponent_argument`. Labels are exactly "For" and "Against" — never "Support" / "Oppose" or "Yes side" / "No side"
6. **Sources** — linked list of all sources used, with bias rating if news source
7. **Expand / collapse** — "Details" toggle reveals full legal text sections if available

**Data completeness states:**
- `"full"` — render all sections normally
- `"partial"` — render available sections, show notice: "Some information for this item wasn't available from our sources."
- `"limited"` — show limited data card (Section 4.4)

### 4.3 Report Card — Race

Each race renders with candidates side by side (desktop) or stacked (mobile).

For each candidate:
1. **Name, party** — no photo (avoids partisan visual framing)
2. **Bio** — max 75 words
3. **Positions on user's priorities** — one row per matched priority topic, sourced
4. **Campaign funding** — total raised (formatted), top 3 donors with amounts

If a position is unknown for a topic: "No public statement found on [topic]." — never omit silently.

### 4.4 Limited Data Card

When `data_completeness: "limited"`:

```
┌────────────────────────────────────────────────┐
│ ⚠️  [Race Title]                               │
│                                                │
│ We have limited information for this race.     │
│ This sometimes happens with local or           │
│ judicial retention races.                      │
│                                                │
│ Candidates: [Name A], [Name B]                 │
│                                                │
│ → View official candidate list                 │
│   (Florida Division of Elections)              │
│ → Check the League of Women Voters guide       │
└────────────────────────────────────────────────┘
```

### 4.5 Staleness Banner

Shown below the report header when `data_freshness !== "fresh"`:

- `"stale"`: Blue info banner — "Some ballot information has been updated since this guide was generated. Refresh your guide for the latest data." with "Refresh" button (navigates back to chat, pre-fills "refresh my guide")
- `"very_stale"`: Yellow warning banner — "This guide is more than 7 days old. Ballot information may have changed significantly." with prominent "Get Updated Guide" button

### 4.6 Shared Report Behavior

When `sessionId` in the URL doesn't match the `session_id` in localStorage (i.e., someone opened a shared link):

Show a disclaimer banner at the top:
```
This ballot guide was personalized for priorities: Housing, Education.
Your ballot items may differ if you live in a different district.
→ Create your own personalized guide
```

No chat interface on shared views — report only.

### 4.7 Print View

Print-specific CSS (`@media print`):
- Hide: header buttons, staleness banner buttons, chat link, footer share controls, expand/collapse toggles
- Show: all expanded card sections (no collapsed state in print)
- Page breaks: before each card (`page-break-before: auto`, avoid breaking inside cards)
- Font size: 12pt
- Color: preserve colored section labels, remove background colors from cards
- URL: print the source URLs as visible text after each source link

---

## 5. Component Structure

```
apps/web/
├── app/
│   ├── layout.tsx             # Root layout, font loading, metadata
│   ├── page.tsx               # Chat view (route: /)
│   ├── report/
│   │   └── [sessionId]/
│   │       └── page.tsx       # Report view (route: /report/[id])
│   └── globals.css            # Tailwind base + CSS variables
├── components/
│   ├── chat/
│   │   ├── ChatView.tsx       # Top-level chat orchestrator
│   │   ├── MessageThread.tsx  # Scrollable message list
│   │   ├── MessageBubble.tsx  # User / assistant / progress bubble
│   │   ├── ProgressBubble.tsx # Streaming progress indicator
│   │   ├── PriorityChips.tsx  # Topic chip selector
│   │   └── InputBar.tsx       # Text input + send button
│   ├── report/
│   │   ├── ReportView.tsx     # Top-level report orchestrator
│   │   ├── ReportHeader.tsx   # Election name, priorities, freshness
│   │   ├── StalenessBar.tsx   # Stale / very_stale banner
│   │   ├── MeasureCard.tsx    # Ballot measure card
│   │   ├── RaceCard.tsx       # Race + candidates card
│   │   ├── CandidatePanel.tsx # One candidate within RaceCard
│   │   ├── LimitedDataCard.tsx# Limited data fallback
│   │   └── SourceList.tsx     # Sources footer within a card
│   └── shared/
│       ├── Header.tsx         # Top nav (wordmark + tagline)
│       └── DisclaimerBanner.tsx # Shared report disclaimer
├── hooks/
│   ├── useSession.ts          # Session init, localStorage, restore
│   ├── useSSEStream.ts        # SSE fetch stream, event parsing
│   └── useReport.ts           # Report fetch + data_freshness
├── lib/
│   ├── api.ts                 # Typed API client (fetch wrappers)
│   ├── types.ts               # TypeScript types mirroring API response schemas
│   └── i18n.ts                # i18n stub (English only for MVP)
├── locales/
│   └── en.json                # All UI strings (no hardcoded strings in components)
└── public/
    └── favicon.ico
```

---

## 6. TypeScript Types

All API response types mirrored in `lib/types.ts`. These must stay in sync with the Python Pydantic schemas in `spec-agent-orchestrator.md`.

```typescript
// Core report types
export interface BallotReport {
  session_id: string;
  generated_at: string;
  election: ElectionSummary;
  precinct: PrecinctInfo;
  user_priorities: string[];
  items: BallotReportItem[];
}

export interface ElectionSummary {
  id: string;       // "FL-2026-GEN"
  name: string;     // "2026 Florida General Election"
  date: string;     // "2026-11-03"
  state: string;    // "FL"
}

export interface PrecinctInfo {
  county: string;
  district: string | null;
  precinct_id: string | null;
}

export interface BallotReportItem {
  item_type: "measure" | "race";
  relevance_score: number;
  relevance_reason: string;
  matched_priorities: string[];
  measure?: MeasureAnalysis;
  race?: RaceAnalysis;
}

export interface MeasureAnalysis {
  measure_id: string;
  short_title: string;
  plain_english_summary: string;
  what_yes_means: string;
  what_no_means: string;
  fiscal_impact: string | null;
  fiscal_impact_source: string | null;
  proponent_argument: string;
  opponent_argument: string;
  proponent_source: string;
  opponent_source: string;
  topic_tags: string[];
  data_completeness: "full" | "partial" | "limited";
  sources: SourceCitation[];
}

export interface RaceAnalysis {
  race_id: string;
  race_title: string;
  race_type: string;
  candidates: CandidateAnalysis[];
  data_completeness: "full" | "partial" | "limited";
  sources: SourceCitation[];
}

export interface CandidateAnalysis {
  candidate_id: string;
  name: string;
  party: string | null;
  bio_summary: string | null;
  positions: Record<string, string>;
  top_donors: string[];
  funding_total: string | null;
  sources: SourceCitation[];
}

export interface SourceCitation {
  name: string;
  url: string;
  bias_rating: string | null;
  fetched_at: string;
}

// SSE event types
export type OrchestratorEvent =
  | IntakeCompleteEvent
  | BallotFoundEvent
  | ItemAnalyzedEvent
  | RankingCompleteEvent
  | ReportCompleteEvent
  | ClarificationNeededEvent
  | ErrorEvent
  | DoneEvent;

export interface IntakeCompleteEvent {
  event_type: "intake_complete";
  session_id: string;
  zip_code: string;
  priorities: string[];
  display_name: string | null;
}

export interface BallotFoundEvent {
  event_type: "ballot_found";
  session_id: string;
  election_name: string;
  item_count: number;
  message: string;
}

export interface ItemAnalyzedEvent {
  event_type: "item_analyzed";
  session_id: string;
  item_id: string;
  item_title: string;
  items_complete: number;
  items_total: number;
}

export interface RankingCompleteEvent {
  event_type: "ranking_complete";
  session_id: string;
  top_item_title: string;
}

export interface ReportCompleteEvent {
  event_type: "report_complete";
  session_id: string;
  report: BallotReport;
}

export interface ClarificationNeededEvent {
  event_type: "clarification_needed";
  session_id: string;
  question: string;
}

export interface ErrorEvent {
  event_type: "error";
  session_id: string;
  error_code: string;
  message: string;
  recoverable: boolean;
}

export interface DoneEvent {
  event_type: "done";
  session_id: string;
  timestamp: string;  // ISO 8601 — consistent with all other event types
}

// Session types
export interface SessionMetadata {
  session_id: string;
  created_at: string;
  updated_at: string;
  display_name: string | null;
  language: string;
  status: "active" | "processing" | "error";
  zip_code: string | null;
  priorities: string[];
  has_report: boolean;
  election_name: string | null;
  message_count: number;
}

export interface ReportResponse {
  session_id: string;
  report: BallotReport;
  generated_at: string;
  data_freshness: "fresh" | "stale" | "very_stale";
  display_name: string | null;
  priorities: string[];
}
```

---

## 7. i18n Architecture

All UI strings live in `locales/en.json`. No string literals in component JSX. This enables Spanish (v2) without touching component code.

```json
// locales/en.json (excerpt)
{
  "chat": {
    "welcome": "Hi — I'm here to help you understand your Florida ballot.",
    "welcome_returning": "Welcome back. Your ballot guide from {date} is ready.",
    "input_placeholder": "Type your zip code or address...",
    "view_report_button": "View Full Ballot Guide →",
    "priority_chips_prompt": "What topics matter most to you this election?",
    "send_chips_button": "See My Ballot Guide"
  },
  "report": {
    "title": "Your Ballot Guide",
    "back_to_chat": "← Back to Chat",
    "print": "Print",
    "generated_on": "Generated {date}",
    "for_label": "For",
    "against_label": "Against",
    "yes_means": "If YES passes",
    "no_means": "If NO wins",
    "fiscal_impact": "Fiscal Impact",
    "fiscal_not_published": "Fiscal impact not yet published.",
    "no_position": "No public statement found on {topic}.",
    "limited_data_title": "Limited information available",
    "sources_label": "Sources"
  },
  "freshness": {
    "stale_message": "Some ballot information has been updated since this guide was generated.",
    "stale_button": "Refresh",
    "very_stale_message": "This guide is more than 7 days old. Ballot information may have changed.",
    "very_stale_button": "Get Updated Guide"
  },
  "shared_report": {
    "disclaimer": "This guide was personalized for priorities: {priorities}. Your ballot items may differ if you live in a different district.",
    "create_own": "Create your own personalized guide"
  },
  "errors": {
    "ballot_not_found": "We couldn't find a ballot for that address. Please check your zip code.",
    "out_of_state": "I'm currently set up for Florida elections only.",
    "generic": "Something went wrong. Please try again.",
    "retry": "Try again"
  },
  "priority_chips": {
    "housing": "🏠 Housing & Rent",
    "education": "🎓 Education & Schools",
    "taxes": "💰 Taxes & Cost of Living",
    "healthcare": "🏥 Healthcare",
    "environment": "🌿 Environment & Climate",
    "public_safety": "🚔 Public Safety & Crime",
    "economy": "💼 Jobs & Economy",
    "voting_rights": "🗳️ Voting & Elections",
    "infrastructure": "🛣️ Infrastructure",
    "senior_services": "👴 Senior Services"
  }
}
```

`lib/i18n.ts` exposes a `t(key, vars?)` function:
```typescript
t("report.no_position", { topic: "Housing" })
// → "No public statement found on Housing."
```

---

## 8. API Client

All fetch calls go through `lib/api.ts`. No `fetch` calls in components or hooks.

```typescript
// lib/api.ts

const BASE = "/api/v1";

export async function createSession(displayName?: string): Promise<SessionMetadata> { ... }

export async function getSession(sessionId: string): Promise<SessionMetadata | null> { ... }

export async function getReport(sessionId: string): Promise<ReportResponse | null> { ... }

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: OrchestratorEvent) => void,
  onDone: () => void
): Promise<void> { ... }
```

`streamMessage` is the only function that uses the streaming fetch pattern. It handles SSE line parsing internally and calls `onEvent` for each parsed event. Components never parse SSE directly.

---

## 9. Design Direction

**Civic, clear, trustworthy.** This is a tool people use on a serious occasion — Election Day. The aesthetic must convey reliability and neutrality without feeling cold or government-bureaucratic.

**Palette:** Off-white background (`#FAFAF8`), near-black text (`#1A1A18`), a single civic blue accent (`#1B4FD8`) for interactive elements. No red/blue partisan color associations. Warm neutrals for cards.

**Typography:** A slightly condensed serif for headings (conveys authority and legibility at larger sizes) paired with a clean geometric sans for body text. Both loaded via `next/font`.

**Cards:** Soft shadow, generous internal padding, clear visual hierarchy. The For / Against sections use a subtle left border — green-tinted for For, no color coding for Against (avoids implying a direction). Both sections same size.

**Progress animation:** During orchestrator processing, a gentle pulsing progress bar in the progress bubble. Item-by-item updates feel responsive without being frantic.

**Print:** Clean newspaper-style layout. Source URLs printed in small gray text after each link.

**Responsive:** Mobile-first. Chat view is single-column on all sizes. Report view stacks candidate panels on mobile, side-by-side on desktop (≥768px).

---

## 10. Acceptance Criteria

### Session lifecycle
- [ ] **AC-FE-01:** On first load with no localStorage, `POST /session` is called and `session_id` stored in localStorage
- [ ] **AC-FE-02:** On reload with existing `session_id`, session metadata is fetched and message history is displayed
- [ ] **AC-FE-03:** On reload with an invalid `session_id` (404 from API), localStorage is cleared and a new session is created
- [ ] **AC-FE-04:** A returning user with `has_report: true` sees a "Welcome back" message and link to their report without re-running the orchestrator

### SSE streaming
- [ ] **AC-FE-05:** Progress bubble updates progressively — each `item_analyzed` event updates the label, it does not wait for `report_complete`
- [ ] **AC-FE-06:** When `report_complete` fires, the progress bubble is replaced by a summary message and "View Full Ballot Guide" button
- [ ] **AC-FE-07:** When `error` event fires, the progress bubble is replaced by the error message with a retry option
- [ ] **AC-FE-08:** The `done` event cleans up any remaining loading state even if no other terminal event was received

### Priority chips
- [ ] **AC-FE-09:** Priority chips appear after `ballot_found` event and disappear after the user submits priorities
- [ ] **AC-FE-10:** Selecting chips and pressing "See My Ballot Guide" sends a correctly formatted message to the API
- [ ] **AC-FE-11:** User can type in the text input instead of using chips — chips are not required

### Report rendering
- [ ] **AC-FE-12:** Every measure card has both `proponent_argument` and `opponent_argument` rendered — never one without the other
- [ ] **AC-FE-13:** Every source in `sources` renders as a clickable link with the source name as text
- [ ] **AC-FE-14:** A measure with `data_completeness: "limited"` renders the `LimitedDataCard`, not the full `MeasureCard`
- [ ] **AC-FE-15:** Report items are rendered in `relevance_score` descending order (highest relevance first)
- [ ] **AC-FE-16:** A candidate position listed as unknown renders "No public statement found on [topic]" — it is never silently omitted

### Staleness and shared reports
- [ ] **AC-FE-17:** A report with `data_freshness: "stale"` shows the blue staleness banner
- [ ] **AC-FE-18:** A report with `data_freshness: "very_stale"` shows the yellow warning banner
- [ ] **AC-FE-19:** A shared report (sessionId not matching localStorage) shows the disclaimer banner
- [ ] **AC-FE-20:** The shared report disclaimer lists the original user's priorities

### i18n
- [ ] **AC-FE-21:** No string literals in JSX — all user-facing text comes from `locales/en.json` via `t()`
- [ ] **AC-FE-22:** `t("report.no_position", { topic: "Housing" })` returns "No public statement found on Housing."

### Print
- [ ] **AC-FE-23:** `@media print` hides navigation buttons and shows all expanded card content
- [ ] **AC-FE-24:** Source URLs are visible as printed text in the print view

---

## 11. Definition of Done

- [ ] All 24 acceptance criteria pass
- [ ] Chat view renders correctly on mobile (375px) and desktop (1280px)
- [ ] Report view renders correctly on mobile and desktop
- [ ] No hardcoded strings in JSX — all via `t()`
- [ ] No `fetch` calls outside `lib/api.ts`
- [ ] TypeScript: zero type errors (`tsc --noEmit` passes)
- [ ] All SSE events handled — no unhandled `event_type` values
- [ ] Print CSS tested via browser print preview — clean output
- [ ] Shared report link behavior tested manually
- [ ] `next build` completes without errors or warnings
- [ ] Lighthouse accessibility score ≥ 90 on both views
- [ ] All interactive elements keyboard-navigable (tab + enter works everywhere)

---

## 12. Test Strategy

### Test file locations
```
apps/web/
├── __tests__/
│   ├── hooks/
│   │   ├── useSession.test.ts
│   │   ├── useSSEStream.test.ts
│   │   └── useReport.test.ts
│   ├── components/
│   │   ├── MeasureCard.test.tsx
│   │   ├── RaceCard.test.tsx
│   │   ├── PriorityChips.test.tsx
│   │   └── StalenessBar.test.tsx
│   └── lib/
│       ├── api.test.ts
│       └── i18n.test.ts
```

**Testing libraries:** Jest + React Testing Library. No Playwright for MVP (add E2E in v2).

### Required test cases

```
# useSession
test_creates_new_session_on_first_load
test_restores_session_from_localstorage
test_clears_localstorage_on_404

# useSSEStream
test_calls_onEvent_for_each_parsed_event
test_calls_onDone_after_done_event
test_handles_malformed_json_without_throwing

# MeasureCard
test_renders_both_proponent_and_opponent
test_renders_limited_data_card_for_limited_completeness
test_renders_fiscal_not_published_when_null
test_renders_all_sources_as_links

# RaceCard
test_renders_no_position_text_for_unknown_position
test_renders_candidates_in_correct_order

# PriorityChips
test_chip_click_toggles_selection
test_submit_sends_formatted_message
test_free_text_works_independently_of_chips

# StalenessBar
test_renders_stale_banner_for_stale
test_renders_warning_banner_for_very_stale
test_renders_nothing_for_fresh

# i18n
test_t_returns_correct_string
test_t_interpolates_variables
test_t_returns_key_for_missing_translation (fallback)
```

---

## 13. Known Constraints (Agent Guardrails)

**DO NOT** hardcode any user-facing string in JSX — use `t()` from `lib/i18n.ts`  
**DO NOT** make `fetch` calls in components — use `lib/api.ts` functions only  
**DO NOT** parse SSE events in components — `useSSEStream` hook handles all parsing  
**DO NOT** store anything in localStorage except `session_id`  
**DO NOT** use a red/blue color scheme — partisan color associations must be avoided  
**DO NOT** label For/Against sections as "Yes side" / "No side" or "Support" / "Oppose" — use exactly "For" and "Against"  
**DO NOT** render one argument without the other — `proponent_argument` and `opponent_argument` always appear as a pair  
**DO NOT** silently omit unknown candidate positions — render the "no public statement" text  
**DO NOT** add a recommendation or "suggested vote" anywhere in the UI — no star ratings, no highlighting of one outcome  
**DO NOT** open the report in a new tab from the "View Full Ballot Guide" button — same tab navigation only  
**DO NOT** call `POST /session` more than once per page load — check localStorage first  

---

## 🎓 Learning Corner

### 🏗️ Architecture Thinking

**Why `fetch` streaming instead of native `EventSource`**

The native `EventSource` browser API is the "right" tool for consuming SSE — it handles reconnection, parses the SSE protocol, and fires typed events. But it only supports GET requests. The message endpoint is a POST (it sends the user's message in the request body). Using a query parameter or URL encoding for the message content would work but is semantically wrong (GET for a state-changing operation), hits URL length limits for long messages, and logs message content in server access logs. The `fetch` with `ReadableStream` approach in Section 3.6 gives full SSE behavior with POST semantics. It's more code than `new EventSource(url)` but it's the correct solution for this use case.

**The `lib/api.ts` boundary — same principle as MCP servers**

The rule "no fetch calls outside `lib/api.ts`" is the frontend equivalent of "no external API calls outside MCP servers" on the backend. Both enforce the same pattern: centralize I/O in one place so that error handling, authentication (when added), request logging, and type validation happen consistently. If a component needs data, it calls an `api.ts` function. If that function needs to change (new auth header, different error handling, base URL change), it changes in one place. Components are pure UI logic. This separation also makes testing dramatically simpler — mock `api.ts`, test components in isolation.

**Two-view architecture and why no state management library**

The app has two views and no shared mutable state between them. The chat view reads from the API and writes via the stream. The report view reads from the API and renders. They communicate only through the URL (`/report/[sessionId]`). There's nothing for Redux or Zustand to manage. Adding a state management library to this app would be like installing a filing system in a studio apartment — technically possible, actively counterproductive. The right amount of state management is the minimum that solves the actual problem. Here, that's `useState` in components and three custom hooks.

### 🤖 AI Engineering Concepts

**Progressive disclosure as the UX pattern for AI latency**

The 40-60 second orchestrator run is too long to show a spinner. The event stream solves this with progressive disclosure: each `item_analyzed` event updates the progress label so the user sees concrete forward motion. "Analyzing Amendment 1 (1/10)..." → "Analyzing Amendment 2 (2/10)..." feels fundamentally different from a blank spinner even if the total time is identical. The psychology is: a spinning indicator says "something is happening, I don't know what." Item-by-item updates say "I found your ballot, I'm working through it, here's exactly where I am." The second experience converts waiting into anticipation.

This pattern — emit granular progress events from the agent, consume them progressively in the UI — is a general design principle for AI features with long latency. It applies to any agent task that has identifiable sub-steps: document analysis, research tasks, code generation. Design the event stream first, then the UI that consumes it.

**Why the frontend types mirror the backend schemas exactly**

`lib/types.ts` contains TypeScript types that mirror the Python Pydantic schemas from `spec-agent-orchestrator.md`. This is intentional redundancy — the same shape defined in two languages. The alternative (TypeScript types auto-generated from the Python schemas) requires tooling that adds complexity and a build step. For MVP with one frontend and one backend team (or one agent building both), maintaining the mirror manually is cheaper. The risk is drift: a Python schema changes and the TypeScript type isn't updated. This risk is mitigated by the TypeScript type errors that surface when you try to render data that doesn't match your types, and by the `tsc --noEmit` check in the Definition of Done. If you add a field to `MeasureAnalysis` in Python, the TypeScript compiler will tell you about every place in the frontend that needs updating.

### 📦 PM/TPM Craft

**i18n as a product decision, not an engineering afterthought**

The decision to externalize all UI strings to `locales/en.json` from day one — even though only English ships in MVP — is a product decision disguised as an engineering one. Here's the real reasoning: Florida's population is 27% Hispanic, with roughly 5 million registered Hispanic voters. Spanish-language ballot guidance is a significant unmet need and a meaningful product differentiator. Building i18n in from day one costs maybe 2 extra days of engineering. Retrofitting it after 6 months of development (when every string is hardcoded) costs weeks and requires touching every component. The `t()` function is a 20-line file. The `locales/en.json` is a one-time setup cost. The payoff when you ship Spanish (v2) is that you translate one JSON file and the entire UI is localized.

For TPMs: when you see an i18n requirement in a spec, resist the urge to descope it. The engineering cost at day one is almost always less than 5% of the total effort. The retrofit cost at month six is almost always more than 20%. Internationalization is the canonical example of a decision that looks optional early and becomes mandatory later at much higher cost.

**The neutrality constraints in the UI spec**

Several constraints in Section 13 (Known Constraints) are directly about neutrality: no red/blue colors, labels are "For" and "Against" (not "Support"/"Oppose"), both arguments always paired, no star ratings, no highlighting of one outcome. These exist because the frontend is the last line of the neutrality contract — even if the agent produces perfectly neutral content, a biased UI can undermine it. A red-colored "Against" section visually signals danger. Labeling sections "Yes side" and "No side" frames the decision as binary combat. Highlighting one candidate's funding in bold implies scrutiny. UI neutrality is harder to enforce than content neutrality because it's implicit — it lives in color choices, label wording, and visual hierarchy, not in text that can be audited. Making these constraints explicit in the spec, the guardrails, and the acceptance criteria is how you prevent them from being decided ad hoc during implementation.

**The print view as a product feature, not an afterthought**

Patricia (the Engaged Retiree) will print this. Carlos might take a screenshot to reference while standing in line at the polling place. Maria might share the link with her spouse. Print and share are the last-mile features that determine whether the ballot guide is actually used on election day — the moment that matters most. The `@media print` CSS in this spec is 20 lines of work. The `data_freshness` staleness check is another 10. The disclaimer banner for shared links is another 15. None of these are technically complex. All of them are the difference between a demo product and a product people trust enough to bring into the voting booth.
