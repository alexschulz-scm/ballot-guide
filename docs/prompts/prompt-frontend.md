# Build Prompt: Frontend

**Component:** `apps/web/`  
**Spec:** `docs/specs/spec-frontend.md`  
**Depends on:** API layer running (or mock), all specs read  
**Estimated sessions:** 4 focused sessions

---

## ⚠️ Before Anything Else

Read these files in order before responding:
1. `CLAUDE.md` (repo root)
2. `docs/specs/spec-frontend.md`
3. `docs/specs/spec-api.md` — Section 2 (endpoints) and Section 3 (SSE format)

Do not write any code. Confirm you have read all files by answering:
- What are the two routes and what does each render?
- Why does the frontend use `fetch` with `ReadableStream` instead of native `EventSource`?
- What does the `done` SSE event tell the frontend to do?
- Name three things the frontend must NEVER render (from the Known Constraints).

---

## PHASE 1 — PLANNING

*No code. Planning output only.*

### Step 1: Component inventory

List every component you will create. For each:
- Which session (A/B/C/D) it belongs to
- What props it accepts (just names and types — one line each)
- Does it fetch data, consume a hook, or is it pure render?

### Step 2: Hook design

For each of the three hooks (`useSession`, `useSSEStream`, `useReport`):
- What state does it manage?
- What side effects does it trigger?
- What does it return to the component that uses it?

### Step 3: SSE parsing plan

Describe the exact sequence of steps in `useSSEStream` from "user submits message" to "report_complete event received." Include: how you initiate the fetch, how you read the stream chunk by chunk, how you handle partial lines at chunk boundaries, and how you map each event type to a UI state update.

### Step 4: i18n plan

Describe how `t("report.no_position", { topic: "Housing" })` works end to end. What does `lib/i18n.ts` contain? How does the function interpolate variables?

### Step 5: Risk identification

Name the 3 most likely failure modes specific to frontend builds by cheap models. For each: what breaks, and what guardrail in the spec prevents it?

### ✋ STOP HERE
Present plan. Wait for approval before writing any code.

---

## PHASE 2 — BUILD

*Execute in Claude Code after plan approval. Sessions in order.*

---

### Session A: Foundation — Types, i18n, API Client

**Goal:** Everything other components depend on. No UI yet.

#### Task A1: TypeScript types

Create `apps/web/lib/types.ts`.

Copy all types from `spec-frontend.md` Section 6 **exactly**. Do not add fields, remove fields, or rename fields. These mirror the Python Pydantic schemas — any deviation causes runtime errors when API responses don't match.

After writing, verify by counting:
- `BallotReport` has exactly these top-level fields: `session_id`, `generated_at`, `election`, `precinct`, `user_priorities`, `items`
- `MeasureAnalysis` has `proponent_argument` AND `opponent_argument` (both — never one)
- `OrchestratorEvent` is a discriminated union of 8 event types

---

#### Task A2: i18n

Create `apps/web/locales/en.json` with all strings from `spec-frontend.md` Section 7.

Create `apps/web/lib/i18n.ts`:

```typescript
import en from "../locales/en.json";

type DeepValue<T> = T extends object
  ? { [K in keyof T]: DeepValue<T[K]> }
  : string;

// Flatten nested keys: "report.no_position" → en.report.no_position
function getNestedValue(obj: Record<string, unknown>, key: string): string {
  const parts = key.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (typeof current !== "object" || current === null) return key;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : key;
}

export function t(key: string, vars?: Record<string, string>): string {
  let value = getNestedValue(en as Record<string, unknown>, key);
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replace(`{${k}}`, v);
    }
  }
  return value;
}
```

**Test immediately:**
```typescript
console.assert(t("report.for_label") === "For");
console.assert(t("report.no_position", { topic: "Housing" }) === "No public statement found on Housing.");
console.assert(t("missing.key") === "missing.key"); // fallback
```

---

#### Task A3: API client

Create `apps/web/lib/api.ts`.

Implement exactly these four functions with these exact signatures:

```typescript
export async function createSession(
  displayName?: string
): Promise<SessionMetadata>

export async function getSession(
  sessionId: string
): Promise<SessionMetadata | null>  // null if 404

export async function getReport(
  sessionId: string
): Promise<ReportResponse | null>   // null if 404 or 202

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: OrchestratorEvent) => void,
  onDone: () => void
): Promise<void>
```

`streamMessage` implementation — use the exact pattern from `spec-frontend.md` Section 3.6:
```typescript
export async function streamMessage(sessionId, content, onEvent, onDone) {
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
        try {
          const event = JSON.parse(line.slice(6)) as OrchestratorEvent;
          if (event.event_type === "done") {
            onDone();
          } else {
            onEvent(event);
          }
        } catch {
          // malformed JSON line — skip silently
        }
      }
    }
  }
}
```

**The buffer logic is critical** — chunk boundaries can split a line mid-character. The `buffer = lines.pop() ?? ""` pattern accumulates incomplete lines until the next chunk completes them. Without this, you'll get intermittent JSON parse errors.

---

#### Task A4: Session A Tests

Create `apps/web/__tests__/lib/api.test.ts` and `apps/web/__tests__/lib/i18n.test.ts`.

**i18n tests (required):**
```
test_t_returns_correct_string_for_known_key
test_t_interpolates_single_variable
test_t_interpolates_multiple_variables
test_t_returns_key_for_unknown_key
test_t_handles_nested_keys
```

**api.ts tests** — mock `fetch` with `jest.spyOn(global, "fetch")`:
```
test_createSession_returns_session_metadata
test_getSession_returns_null_on_404
test_getReport_returns_null_on_404
test_getReport_returns_null_on_202
test_streamMessage_calls_onEvent_for_each_data_line
test_streamMessage_calls_onDone_on_done_event
test_streamMessage_skips_malformed_json
test_streamMessage_handles_split_chunks
```

The split-chunk test is important — simulate a chunk that ends mid-JSON line:
```typescript
// Mock response body that delivers split chunks
const chunks = [
  'event: item_analyzed\ndata: {"event_type":"item_an',  // split mid-JSON
  'alyzed","session_id":"x","item_id":"1","item_title":"Amendment 1","items_complete":1,"items_total":4}\n\n',
];
```

Run: `jest apps/web/__tests__/lib/` — all pass before Session B.

---

### Session B: Hooks

**Goal:** All three hooks, fully tested. No UI components yet.

#### Task B1: useSession

Create `apps/web/hooks/useSession.ts`.

```typescript
export function useSession() {
  // Returns:
  // sessionId: string | null
  // session: SessionMetadata | null
  // isLoading: boolean
  // error: string | null
}
```

**Behavior on mount:**
1. Read `session_id` from `localStorage.getItem("ballot_guide_session_id")`
2. If found: call `getSession(id)`
   - If returns metadata → set `session` state
   - If returns null (404) → clear localStorage, call `createSession()`, store new id
3. If not found: call `createSession()`, store new id in localStorage

**Key:** `"ballot_guide_session_id"` — use this exact key, no other localStorage usage.

```typescript
// localStorage key — defined once, used everywhere
export const SESSION_KEY = "ballot_guide_session_id";
```

---

#### Task B2: useSSEStream

Create `apps/web/hooks/useSSEStream.ts`.

```typescript
export function useSSEStream(sessionId: string | null) {
  // Returns:
  // sendMessage: (content: string) => void
  // events: OrchestratorEvent[]
  // latestEvent: OrchestratorEvent | null
  // isStreaming: boolean
  // streamError: string | null
  // clearEvents: () => void
}
```

**State management:**
- `events` accumulates all events received in the current stream
- `latestEvent` is the most recent event (for progress label updates — avoids scanning events array)
- `isStreaming` is `true` from first `sendMessage` call until `onDone` fires
- `clearEvents` resets state for a new stream (called before each `sendMessage`)

**`sendMessage` implementation:**
```typescript
const sendMessage = (content: string) => {
  if (!sessionId || isStreaming) return;
  clearEvents();
  setIsStreaming(true);
  streamMessage(
    sessionId,
    content,
    (event) => {
      setEvents(prev => [...prev, event]);
      setLatestEvent(event);
    },
    () => {
      setIsStreaming(false);
    }
  ).catch(err => {
    setStreamError("Connection lost. Please try again.");
    setIsStreaming(false);
  });
};
```

---

#### Task B3: useReport

Create `apps/web/hooks/useReport.ts`.

```typescript
export function useReport(sessionId: string | null) {
  // Returns:
  // report: BallotReport | null
  // freshness: "fresh" | "stale" | "very_stale" | null
  // isLoading: boolean
  // error: string | null
  // refetch: () => void
}
```

Calls `getReport(sessionId)` on mount and when `refetch` is called. Handles `null` response (report not ready) without error.

---

#### Task B4: Session B Tests

Create `apps/web/__tests__/hooks/` tests for all three hooks.

Use `@testing-library/react` `renderHook` for hook tests. Mock `lib/api.ts` entirely:
```typescript
jest.mock("../../lib/api");
```

**useSession tests (required):**
```
test_creates_new_session_when_no_localstorage
test_stores_session_id_in_localstorage_after_create
test_restores_existing_session_from_localstorage
test_clears_localstorage_and_creates_new_on_404
```

**useSSEStream tests (required):**
```
test_isStreaming_false_initially
test_isStreaming_true_after_sendMessage
test_isStreaming_false_after_done
test_events_accumulate_across_stream
test_latestEvent_updates_on_each_event
test_clearEvents_resets_state
test_streamError_set_on_fetch_failure
```

**useReport tests (required):**
```
test_fetches_report_on_mount
test_returns_null_when_report_not_ready
test_refetch_triggers_new_fetch
```

Run: `jest apps/web/__tests__/hooks/` — all pass before Session C.

---

### Session C: Report View Components

**Goal:** The full Report View, pixel-complete.  
**Depends on:** Sessions A and B complete.  
**Rule:** No hardcoded strings. Every user-facing string uses `t()`.

#### Task C1: SourceList

Create `apps/web/components/report/SourceList.tsx`.

Simplest component — start here to validate the pattern:
```typescript
interface Props {
  sources: SourceCitation[];
}
```
Renders each source as a link: `<a href={source.url} target="_blank" rel="noopener noreferrer">{source.name}</a>`. Shows `bias_rating` in parentheses if present.

---

#### Task C2: LimitedDataCard

Create `apps/web/components/report/LimitedDataCard.tsx`.

```typescript
interface Props {
  title: string;
  candidateNames: string[];
}
```

Renders the limited data UI from `spec-frontend.md` Section 4.4. Hardcode the two external links (FL Division of Elections, League of Women Voters) as constants at the top of the file — not in i18n, these are proper nouns / URLs.

---

#### Task C3: CandidatePanel

Create `apps/web/components/report/CandidatePanel.tsx`.

```typescript
interface Props {
  candidate: CandidateAnalysis;
  priorities: string[];  // user's priorities — determines which positions to show
}
```

For each priority in `priorities`, show the candidate's position if present, or `t("report.no_position", { topic: priority })` if not. **Never omit silently.**

Funding section: format `funding_total` as currency if present. Show `top_donors` as a comma-separated list.

---

#### Task C4: MeasureCard

Create `apps/web/components/report/MeasureCard.tsx`.

```typescript
interface Props {
  item: BallotReportItem;  // item_type === "measure"
  priorities: string[];
}
```

**If `data_completeness === "limited"`: render `<LimitedDataCard>` instead.**

Otherwise render all sections in spec order (Section 4.2):
1. Header with relevance tag
2. Summary
3. What yes/no means
4. Fiscal impact (or `t("report.fiscal_not_published")` if null)
5. For / Against — BOTH always present, same visual weight
6. Sources
7. Expand/collapse for full text (if `measure_text` present)

**Critical:** `proponent_argument` and `opponent_argument` must render as a pair — same container, same visual weight. If either is missing (shouldn't happen given schema enforcement, but be defensive), show "Not available" for that section rather than removing the other.

---

#### Task C5: RaceCard

Create `apps/web/components/report/RaceCard.tsx`.

```typescript
interface Props {
  item: BallotReportItem;  // item_type === "race"
  priorities: string[];
}
```

If `data_completeness === "limited"`: render `<LimitedDataCard>`.

Otherwise: render each candidate using `<CandidatePanel>`. Side-by-side on desktop (`md:flex-row`), stacked on mobile (`flex-col`).

---

#### Task C6: StalenessBar

Create `apps/web/components/report/StalenessBar.tsx`.

```typescript
interface Props {
  freshness: "fresh" | "stale" | "very_stale";
  onRefresh: () => void;
}
```

- `"fresh"` → renders nothing (return `null`)
- `"stale"` → blue info banner with refresh button
- `"very_stale"` → yellow warning banner with "Get Updated Guide" button

---

#### Task C7: ReportHeader

Create `apps/web/components/report/ReportHeader.tsx`.

```typescript
interface Props {
  report: BallotReport;
  freshness: "fresh" | "stale" | "very_stale";
  isShared: boolean;
  onRefresh: () => void;
}
```

Renders: election name, priorities list, generated date. If `isShared`, shows `DisclaimerBanner`. Renders `StalenessBar` below header.

---

#### Task C8: ReportView

Create `apps/web/components/report/ReportView.tsx` and `apps/web/app/report/[sessionId]/page.tsx`.

`ReportView` orchestrates:
1. Call `useReport(sessionId)`
2. Determine `isShared` by comparing `sessionId` with `localStorage.getItem(SESSION_KEY)`
3. Render `ReportHeader`
4. Map `report.items` (already ordered by `relevance_score` descending from API) to `MeasureCard` or `RaceCard`

**Do not re-sort items** — the API returns them in correct order. Trust the order.

The Next.js page component:
```typescript
// app/report/[sessionId]/page.tsx
export default function ReportPage({ params }: { params: { sessionId: string } }) {
  return <ReportView sessionId={params.sessionId} />;
}
```

---

#### Task C9: Print CSS

Add to `apps/web/app/globals.css`:
```css
@media print {
  .no-print { display: none !important; }
  .print-expand { display: block !important; }  /* force expanded state */
  
  /* Show URLs after links */
  a[href]::after {
    content: " (" attr(href) ")";
    font-size: 10pt;
    color: #666;
  }
  
  /* Avoid breaking cards across pages */
  .ballot-card {
    page-break-inside: avoid;
    break-inside: avoid;
  }
  
  /* Base print styles */
  body { font-size: 12pt; background: white; }
  .ballot-card { border: 1px solid #ccc; box-shadow: none; }
}
```

Add `no-print` class to: navigation buttons, staleness banner buttons, collapse toggles, footer share controls.
Add `ballot-card` class to: `MeasureCard` and `RaceCard` root elements.

---

#### Task C10: Session C Tests

Create `apps/web/__tests__/components/` tests.

**Required tests:**
```
# MeasureCard
test_renders_both_for_and_against_sections
test_renders_limited_data_card_for_limited_completeness
test_renders_fiscal_not_published_when_null
test_all_sources_render_as_links
test_for_and_against_labels_exact (not "Support"/"Oppose")

# RaceCard
test_renders_candidate_panels_for_each_candidate
test_renders_limited_data_card_for_limited

# CandidatePanel
test_renders_no_position_text_for_missing_topic
test_never_silently_omits_priority_topic

# StalenessBar
test_renders_nothing_for_fresh
test_renders_blue_banner_for_stale
test_renders_yellow_banner_for_very_stale

# ReportView
test_renders_items_in_api_order (no re-sorting)
test_shows_disclaimer_for_shared_session
```

Run: `jest apps/web/__tests__/components/` — all pass before Session D.

---

### Session D: Chat View and Wiring

**Goal:** Chat view complete, full end-to-end flow working.  
**Depends on:** Sessions A, B, C complete.

#### Task D1: ProgressBubble

Create `apps/web/components/chat/ProgressBubble.tsx`.

```typescript
interface Props {
  latestEvent: OrchestratorEvent | null;
  isStreaming: boolean;
}
```

Maps event types to status labels using `t()`:
```typescript
function getStatusLabel(event: OrchestratorEvent | null): string {
  if (!event) return t("chat.progress.starting");
  switch (event.event_type) {
    case "intake_complete": return t("chat.progress.found_ballot");
    case "ballot_found": return `${t("chat.progress.analyzing")} ${event.item_count} items...`;
    case "item_analyzed": return `${t("chat.progress.analyzing_item", { title: event.item_title })} (${event.items_complete}/${event.items_total})`;
    case "ranking_complete": return t("chat.progress.ranking");
    default: return t("chat.progress.working");
  }
}
```

Add these keys to `locales/en.json` under `"chat.progress"`.

Shows animated progress bar while `isStreaming`. Disappears (returns `null`) when `!isStreaming`.

---

#### Task D2: PriorityChips

Create `apps/web/components/chat/PriorityChips.tsx`.

```typescript
interface Props {
  onSubmit: (message: string) => void;
  visible: boolean;
}
```

Internal state: `selected: string[]` — array of taxonomy keys.

On "See My Ballot Guide" press:
```typescript
const message = selected.length > 0
  ? `I care about: ${selected.map(k => t(`priority_chips.${k}`)).join(", ")}`
  : "";
// Only submit if user selected chips or typed something
```

Renders `null` when `visible === false`.

---

#### Task D3: MessageBubble

Create `apps/web/components/chat/MessageBubble.tsx`.

```typescript
interface Props {
  role: "user" | "assistant";
  content: string;
}
```

User bubbles: right-aligned, plain text.
Assistant bubbles: left-aligned, renders markdown. Use a lightweight markdown renderer — either `react-markdown` (if available) or manual rendering for the subset used (bold, lists, links).

Do not use a full markdown library that requires complex setup. If `react-markdown` is not in `package.json`, render plain text with newlines converted to `<br>` tags.

---

#### Task D4: InputBar

Create `apps/web/components/chat/InputBar.tsx`.

```typescript
interface Props {
  onSend: (content: string) => void;
  disabled: boolean;
  placeholder?: string;
}
```

Text field + send button. Send on button click or Enter key. Clears field after send. Disabled when `disabled === true` (stream in progress).

---

#### Task D5: MessageThread

Create `apps/web/components/chat/MessageThread.tsx`.

```typescript
interface Props {
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  latestEvent: OrchestratorEvent | null;
  isStreaming: boolean;
  showViewReportButton: boolean;
  sessionId: string;
}
```

Renders message history as `MessageBubble` components. If `isStreaming`, shows `ProgressBubble` at the bottom. If `showViewReportButton`, shows the "View Full Ballot Guide →" button linking to `/report/[sessionId]`.

Auto-scrolls to bottom when new messages or events arrive:
```typescript
const bottomRef = useRef<HTMLDivElement>(null);
useEffect(() => {
  bottomRef.current?.scrollIntoView({ behavior: "smooth" });
}, [messages, latestEvent]);
```

---

#### Task D6: ChatView

Create `apps/web/components/chat/ChatView.tsx` and `apps/web/app/page.tsx`.

`ChatView` orchestrates everything:

```typescript
export function ChatView() {
  const { sessionId, session } = useSession();
  const { sendMessage, latestEvent, events, isStreaming } = useSSEStream(sessionId);
  
  const [messages, setMessages] = useState<Message[]>([]);
  const [showChips, setShowChips] = useState(false);
  const [showViewReport, setShowViewReport] = useState(false);
  
  // Show chips after ballot_found event
  useEffect(() => {
    const lastEvent = events[events.length - 1];
    if (lastEvent?.event_type === "ballot_found") setShowChips(true);
    if (lastEvent?.event_type === "report_complete") {
      setShowChips(false);
      setShowViewReport(true);
      // Add the report summary as an assistant message
      setMessages(prev => [...prev, {
        role: "assistant",
        content: buildReportSummary(lastEvent.report)
      }]);
    }
  }, [events]);
  
  const handleSend = (content: string) => {
    setMessages(prev => [...prev, { role: "user", content }]);
    setShowChips(false);
    sendMessage(content);
  };
  
  // Restore message history on session load
  // ... 
}
```

`buildReportSummary` — a pure function that converts a `BallotReport` into a conversational text summary (top 3 most relevant items, plain English). This is not AI-generated — it's template-based:
```typescript
function buildReportSummary(report: BallotReport): string {
  const top3 = report.items.slice(0, 3);
  const intro = `Your ballot has ${report.items.length} items. Based on your priorities, here's what stands out:\n\n`;
  const items = top3.map(item => {
    const title = item.measure?.short_title ?? item.race?.race_title ?? "Unknown";
    return `**${title}** — ${item.relevance_reason}`;
  }).join("\n\n");
  return intro + items + `\n\nWant to go deeper on any of these, or [view your full ballot guide](/report/${report.session_id})?`;
}
```

The Next.js page:
```typescript
// app/page.tsx
export default function Home() {
  return <ChatView />;
}
```

---

#### Task D7: Root Layout and Globals

Create `apps/web/components/shared/Header.tsx` — the Ballot Guide wordmark and tagline shown at the top of the Chat View (the Report View uses its own `ReportHeader`). Keep it simple: wordmark in the heading font, tagline beneath in body font, no navigation links. Used only in `ChatView`.

Create `apps/web/app/layout.tsx`:
```typescript
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ballot Guide — Understand your Florida ballot",
  description: "Personalized, neutral ballot guidance for Florida voters.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

Update `apps/web/app/globals.css` with:
- Tailwind directives (`@tailwind base/components/utilities`)
- CSS variables for the color palette from `spec-frontend.md` Section 9
- Print CSS from Task C9
- Font loading (use `next/font` — pick a condensed serif for headings, geometric sans for body)

---

#### Task D8: next.config and API proxy

Create `apps/web/next.config.js`:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.API_URL || "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
```

This proxies `/api/v1/*` from the Next.js dev server to the FastAPI backend. In production, configure via environment variable `API_URL`.

---

#### Task D9: Session D Tests

```
# PriorityChips
test_chip_click_toggles_selection
test_multiple_chips_can_be_selected
test_submit_formats_message_correctly
test_free_text_input_works_without_chip_selection
test_renders_null_when_not_visible

# ChatView integration
test_shows_chips_after_ballot_found_event
test_hides_chips_after_submit
test_shows_view_report_button_after_report_complete
test_adds_user_message_to_thread_on_send
test_input_disabled_while_streaming

# MessageThread
test_scrolls_to_bottom_on_new_message
test_shows_progress_bubble_while_streaming
test_hides_progress_bubble_after_done
```

---

## Final Verification

```bash
# Type check
cd apps/web && npx tsc --noEmit

# Tests
jest --passWithNoTests

# Build
npm run build
```

Then manually verify:
1. Start API with `docker compose up`
2. Start frontend with `npm run dev`
3. Open `http://localhost:3000` — confirm welcome message appears
4. Type a zip code — confirm stream starts and progress updates
5. After guide loads — click "View Full Ballot Guide" — confirm report renders
6. Open report URL in incognito — confirm shared disclaimer appears
7. Print preview — confirm clean layout, source URLs visible

---

## If You Get Stuck

**"SSE events arrive all at once, not progressively"**  
→ This is the API-side nginx buffering issue (`X-Accel-Buffering`), not a frontend problem. Check that the API is returning the header. In local dev without nginx this won't appear — test against staging.

**"JSON parse error intermittently on SSE events"**  
→ Chunk boundary split. Make sure the buffer accumulation pattern from Task A3 is implemented exactly. The `buffer = lines.pop() ?? ""` line is the critical piece.

**"useSession creates a new session on every render"**  
→ The `createSession` / `getSession` call must be inside a `useEffect` with `[]` dependencies — not in the render body. If you're seeing multiple sessions created, you have a missing dependency array.

**"Priority chips don't disappear after submission"**  
→ `setShowChips(false)` must be called in `handleSend` before `sendMessage`, not inside the event handler. The chips should hide immediately when the user submits, not wait for the stream.

**"Report items are in wrong order"**  
→ Do NOT sort items in the frontend. The API returns them sorted by `relevance_score` descending. Re-sorting in the frontend introduces bugs when scores are equal. Trust the API order.

**"`t()` returns the key instead of the string"**  
→ The key path doesn't match the JSON structure. `t("chat.progress.starting")` requires `en.json` to have `{"chat": {"progress": {"starting": "..."}}}`. Check the nesting matches exactly.

**"TypeScript errors on `report.items.map`"**  
→ `BallotReportItem` has `measure?` and `race?` as optional fields. Use type narrowing: `if (item.item_type === "measure" && item.measure)` before accessing `item.measure` fields.

**"`next build` fails with 'window is not defined'"**  
→ `localStorage` access inside `useSession` must be inside `useEffect` or guarded with `typeof window !== "undefined"`. Next.js runs components on the server during build — `localStorage` doesn't exist server-side.
