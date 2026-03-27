<!-- Generated: 2026-03-27 | Files scanned: 30+ | Token estimate: ~700 -->

# Frontend Architecture

## Page Tree

```
app/
  layout.tsx          Root layout (Geist font, metadata)
  page.tsx            Home -> renders <ChatView/>
  report/
    [sessionId]/
      page.tsx        Dynamic report page
```

## Component Hierarchy

```
ChatView (157 lines) -- main chat interface, SSE event handler
  +-- Header (29) -- top nav
  +-- ElectionSelector (48) -- election picker dropdown
  +-- MessageThread (52) -- message list
  |     +-- MessageBubble (157) -- styled message with markdown
  |     +-- ProgressBubble (42) -- loading/progress indicator
  +-- PriorityChips (73) -- priority tag display
  +-- InputBar (53) -- text input + send button

ReportView (75) -- full report container
  +-- ReportHeader (86) -- title, election info, freshness
  +-- StalenessBar (35) -- visual freshness indicator
  +-- MeasureCard (91) -- ballot measure/amendment
  |     +-- SourceList (66) -- citations with bias ratings
  +-- RaceCard (61) -- candidate race
  |     +-- CandidatePanel (52) -- single candidate details
  |     +-- ComparisonTable (87) -- side-by-side comparison
  |     +-- SourceList (66)
  +-- LimitedDataCard (46) -- incomplete data notice
```

## Hooks

| Hook | Lines | Purpose |
|------|-------|---------|
| useSession.ts | 73 | Session lifecycle, localStorage persistence (SESSION_KEY, ELECTION_KEY) |
| useReport.ts | 45 | Report fetching, freshness tracking ("fresh"/"stale"/"very_stale") |
| useSSEStream.ts | 47 | POST-based SSE streaming, newline-delimited JSON parsing |

## Lib

| File | Lines | Purpose |
|------|-------|---------|
| api.ts | 113 | All fetch calls (listElections, createSession, getSession, getReport, streamMessage) |
| types.ts | 213 | TypeScript types mirroring backend schemas (discriminated union on event_type) |
| i18n.ts | 28 | t() function with en.json locale, {var} interpolation |

## Stack

- Next.js 16.1.6, React 19.2.3, TypeScript 5
- Tailwind CSS 4 (via @tailwindcss/postcss)
- Jest 30 + @testing-library/react 16 (13 test files)
- Dev port: 3001

## Key Rules

- No fetch in components -- only in lib/api.ts
- No SSE parsing in components -- only in useSSEStream hook
- No localStorage outside useSession (and only inside useEffect)
- No red/blue partisan colors -- civic palette only
- "For"/"Against" labels (never "Support"/"Oppose")
- Report items rendered in API order (no re-sorting)
- proponent_argument + opponent_argument always render as a pair
