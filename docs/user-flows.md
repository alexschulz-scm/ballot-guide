# User Flows & Scenarios

This document defines the key user journeys for Ballot Guide MVP. These flows drive the UX design, agent behavior, API design, and acceptance criteria for each epic.

---

## User Personas

### Maria — The Busy Parent
46, Tampa. Works full time, two kids in public school. Votes every major election but rarely looks at down-ballot races or amendments. Cares deeply about education and housing costs. Has 15 minutes before the kids get home.

### James — The First-Time Voter
22, Miami. Just registered. Overwhelmed by the ballot. Doesn't know what most of the amendments mean. Doesn't identify strongly with either party. Wants to make an informed decision but doesn't know where to start.

### Patricia — The Engaged Retiree
68, Jacksonville. Votes in every election including primaries. Already has opinions but wants to make sure she understands what the measures actually say in plain language, not political spin. Skeptical of AI. Will check sources.

### Carlos — The Undecided Voter
38, Orlando. Registered independent. Cares about small business taxes and public safety. Gets overwhelmed by partisan framing and wants just the facts. May use the guide on election day morning.

---

## Core User Flows

---

### Flow 1: First-Time Session — Full Ballot Guide

**Persona:** James, Maria, Carlos
**Entry point:** Landing page
**Goal:** Receive a personalized ballot guide from scratch

```
Step 1 — Landing
  User arrives at ballot-guide.app
  Sees: brief value proposition ("Understand your ballot in plain language")
  Sees: single prompt: "Tell me your address and what matters most to you"
  No signup required. Session created anonymously.

Step 2 — Address Input
  User types: "I live in Miami, zip 33101"
  OR: "I'm in Tampa, 33602"
  System: resolves to precinct, identifies election, confirms ballot found
  Response: "Got it — I found your ballot for the [Election Name]. 
             Before I dig in, what topics matter most to you this election?"

Step 3 — Priority Collection
  User types priorities in natural language:
    "I care about housing costs and my kids' school"
    OR "taxes and crime"
    OR "environment and healthcare"
  System extracts structured priorities (2–5 topics)
  System confirms: "Got it — I'll focus on housing and education. 
                   Your ballot has [N] items. Let me put together your guide."

Step 4 — Processing (streaming)
  System shows progress: "Looking up your ballot... analyzing measures... 
                          summarizing candidates..."
  Streams partial results as they complete
  Takes 20–40 seconds for full ballot

Step 5 — Conversational Summary
  System delivers top 3 most relevant items conversationally:
  "Your ballot has 4 constitutional amendments and 6 races. 
   Based on your interest in housing and education, here's what stands out:
   
   Amendment 3 directly affects housing — it would [plain summary].
   The State Senate race in your district has candidates with very different 
   positions on school funding...
   
   Want me to go deeper on any of these, or see your full ballot guide?"

Step 6 — Full Report
  User clicks "View Full Ballot Guide" or types "show me everything"
  Report view opens: structured, printable, all items ranked by relevance
  Each item: summary / fiscal / pro / con / relevance / sources
```

**Success criteria:**
- Full guide generated in < 60 seconds
- All items on official ballot represented
- No recommendations present in output
- Every factual claim has a source link
- User can navigate from chat to report and back

---

### Flow 2: Deep Dive on a Specific Item

**Persona:** Patricia, Carlos
**Entry point:** After initial guide is generated OR direct question
**Goal:** Understand one ballot item in depth

```
Step 1 — User asks about a specific item
  "Tell me more about Amendment 2"
  "What does the minimum wage amendment actually say?"
  "Who is funding the campaign for Prop X?"
  "What do DeSantis and Crist say about education?"

Step 2 — Agent fetches full detail
  Retrieves full legal text of measure
  Fetches official proponent/opponent arguments
  Fetches campaign finance data for candidates
  Fetches recent news coverage with source labels

Step 3 — Detailed response
  Plain English breakdown of the measure text section by section
  Official pro/con arguments quoted and attributed
  Funding sources: top donors to each side
  News coverage: what different outlets reported (with bias labels)
  
  For candidates: side-by-side position comparison on the topic
  "On education funding, Candidate A has said [quote, source]. 
   Candidate B's position is [quote, source]."

Step 4 — Follow-up questions
  User can ask follow-ups:
  "What was the fiscal impact estimate?"
  "Who wrote the proponent argument?"
  "Has something like this passed in other states?"
  System answers from cached data or fetches if needed
```

**Success criteria:**
- Full legal text available and summarized section by section
- Official arguments quoted verbatim and sourced
- Campaign finance shows top donors, not just totals
- Follow-up questions answered without re-running full pipeline
- Patricia can verify every claim by clicking source links

---

### Flow 3: Comparison Mode — Candidates Side by Side

**Persona:** Carlos, Maria
**Entry point:** Any race in the ballot guide
**Goal:** Understand where two candidates differ on topics the user cares about

```
Step 1 — User requests comparison
  "Compare the governor candidates on housing"
  "What's the difference between the two senate candidates?"
  "Show me where they disagree"

Step 2 — Agent builds comparison
  Fetches positions for each candidate on each of user's priority topics
  Sources: candidate websites, official statements, voting records, debate quotes
  
Step 3 — Side-by-side output
  Rendered as a comparison table or parallel sections:
  
  Topic: Housing / Rent Control
  Candidate A: [stated position + source]
  Candidate B: [stated position + source]
  
  Topic: Education Funding
  Candidate A: [stated position + source]
  Candidate B: [stated position + source]
  
  No synthesis that implies one is better. 
  Gaps acknowledged: "No public statement found on this topic."

Step 4 — Funding context
  "Here's who is funding each campaign:"
  Top 5 donor categories for each candidate, sourced from OpenSecrets/FL EFIS
```

**Success criteria:**
- Every stated position linked to a primary source
- Missing positions explicitly noted (not silently omitted)
- Funding data present for major races
- No language implying one candidate's position is better or more consistent

---

### Flow 4: Quick Lookup — Election Day Morning

**Persona:** Carlos
**Entry point:** Returning user, election day
**Goal:** Quick reminder of what's on the ballot, no time for deep research

```
Step 1 — Returning session
  User returns with existing session (session ID in localStorage)
  System recognizes session: "Welcome back. Your ballot guide from [date] is ready."
  
  OR new session: user types "I need a quick summary of my ballot, I'm voting today"

Step 2 — Accelerated flow
  System skips re-explaining, shows concise version:
  "You have [N] items on your ballot. Here's the quick version:
  
  Amendment 2 — Minimum wage increase. YES: raises wages. NO: keep current law.
  Amendment 3 — Recreational marijuana. YES: legalizes. NO: keeps current restrictions.
  Governor: [Name A] (R) vs [Name B] (D). [One-sentence each on education, housing]
  ..."

Step 3 — Optional drill-down
  "Tap any item for more detail"
  System can go deep on demand but defaults to brief for this mode
```

**Success criteria:**
- Returning session loads in < 5 seconds
- Quick summary fits on one screen
- One-tap to drill into any item
- No more cognitive load than necessary on a busy morning

---

### Flow 5: Explainer Mode — "What Does This Mean?"

**Persona:** James (first-time voter)
**Entry point:** Any point in the conversation
**Goal:** Understand civics / process / terminology, not just the specific ballot

```
Step 1 — User asks a context question
  "What's a constitutional amendment vs a regular law?"
  "What does 'judicial retention' mean?"
  "If an amendment passes, can it be changed later?"
  "What's the difference between the state house and state senate?"

Step 2 — Factual civics explanation
  System answers with a clear, neutral explanation
  No political framing
  Follows up: "Now, on your ballot there's Amendment X, which is a [type]. Want me to explain what it would do?"

Step 3 — Bridge back to ballot
  Ties the civics explainer back to items on their specific ballot
  Keeps the user in context without overwhelming them
```

**Success criteria:**
- Civics questions answered accurately without condescension
- Always bridges back to the user's specific ballot
- James feels equipped, not lectured

---

### Flow 6: Report Export & Sharing

**Persona:** Patricia, Maria
**Entry point:** Full report view
**Goal:** Save or share the ballot guide

```
Step 1 — User wants to save or share
  "Can I print this?"
  "I want to send this to my husband"
  "Can I save this as a PDF?"

Step 2 — Export options
  Print-optimized CSS renders cleanly (no chat UI chrome)
  "Copy link" generates a shareable URL for this session's report
  PDF export via browser print dialog (no server-side PDF generation for MVP)

Step 3 — Shared link behavior
  Recipient opens link → sees full report (read-only, no chat)
  Report is not personalized to recipient — it shows the original user's priorities
  Disclaimer: "This guide was personalized for priorities: [housing, education]. 
               Your ballot items may differ if you live in a different district."
```

**Success criteria:**
- Print view is clean and readable
- Shareable link works without login
- Disclaimer present on shared reports
- No user data shared beyond ballot content and stated priorities

---

## Edge Cases & Error Flows

### Address Not Found
```
User: "I live in Florida"
System: "I need a more specific address or zip code to find your exact ballot. 
         Florida has hundreds of different local races depending on your county 
         and district. What's your zip code?"
```

### Address Outside Florida (MVP scope)
```
User: "33101" → Miami → ✅
User: "10001" → New York → 
System: "I'm currently set up for Florida elections only. 
         I found some Florida-based civic resources if helpful, 
         but I can't generate a ballot guide for New York yet."
```

### Election Not Yet Finalized (candidates still filing)
```
System: "The 2026 Florida ballot isn't finalized yet — candidate filing closes [date]. 
         I can show you what's confirmed so far and flag items that may still change."
```

### Data Unavailable for a Specific Race
```
System: "I found this race on your ballot but couldn't retrieve candidate details 
         from my sources. This sometimes happens with local judicial races. 
         Here's the official Florida Elections source: [link]"
```

### User Asks for a Recommendation
```
User: "Just tell me who to vote for"
System: "That's not something I'll do — my job is to make sure you have the clearest 
         possible picture of what's on your ballot so you can decide for yourself. 
         What I can do is show you exactly where each candidate stands on the things 
         you told me matter to you. Want me to do that?"
```

### User Expresses Strong Political Opinion
```
User: "I hate [party/candidate], just tell me how to vote against them"
System: "I hear you. I'll stick to facts about what's on your ballot — 
         I'm not going to tell you who to vote for or against. 
         But I can tell you exactly what each candidate's stated positions are 
         and who's funding their campaign. Want me to pull that up?"
```

---

## User Flow → Feature Matrix

| Feature | Flow 1 | Flow 2 | Flow 3 | Flow 4 | Flow 5 | Flow 6 |
|---------|--------|--------|--------|--------|--------|--------|
| Address resolution | ✅ | | | ✅ | | |
| Priority collection | ✅ | | | | | |
| Ballot lookup | ✅ | | | ✅ | | |
| Measure summary | ✅ | ✅ | | ✅ | | |
| Measure full text | | ✅ | | | | |
| Candidate profile | ✅ | ✅ | ✅ | ✅ | | |
| Candidate comparison | | | ✅ | | | |
| Campaign finance | | ✅ | ✅ | | | |
| News coverage | | ✅ | | | | |
| Civics explainer | | | | | ✅ | |
| Relevance ranking | ✅ | | | ✅ | | |
| Report view | ✅ | | | ✅ | | ✅ |
| Export / share | | | | | | ✅ |
| Returning session | | | | ✅ | | |

---

## Decisions

### 1. Priority Collection — Hybrid Model ✅
Use a hybrid approach: conversation starters (pre-built topic chips) as the default, plus free-text input for users who want to express something not in the list. Free text is normalized to the internal topic taxonomy by the intake agent before processing.

**Conversation starter chips (MVP set):**
- 🏠 Housing & Rent
- 🎓 Education & Schools
- 💰 Taxes & Cost of Living
- 🏥 Healthcare
- 🌿 Environment & Climate
- 🚔 Public Safety & Crime
- 💼 Jobs & Economy
- 🗳️ Voting & Elections
- 🛣️ Infrastructure & Transportation
- 👴 Senior Services & Medicare

User can select multiple chips, type freely, or both. Free text input preserved and shown back to user alongside normalized topics.

**Internal topic taxonomy** (what the system maps everything to — drives relevance ranking):
`housing`, `education`, `taxes`, `healthcare`, `environment`, `public_safety`, `economy`, `voting_rights`, `infrastructure`, `senior_services`

### 2. Session Persistence ✅
Sessions persist indefinitely. On return visit:
- If ballot data is unchanged → serve cached report instantly with "Last updated [date]" label
- If ballot data has changed (candidate added/dropped, measure text updated) → show staleness banner: "Some information on your ballot has been updated since your last visit. Refresh your guide?"
- Staleness check is a lightweight query against `api_cache` TTL, not a full re-run

### 3. Multi-Person Households ✅
- Name is optional at session start ("What should I call you?" — skippable)
- Each person gets their own session (mobile-first assumption — one phone per person)
- Shared report links are read-only and labeled with the originating user's name if provided: "Maria's Ballot Guide"
- No household grouping feature for MVP. Each session is independent.
- Architecture note: `sessions` table has optional `display_name` field. No account linking.

### 4. Local Races — Limited Data State ✅
Show a "Limited Data" indicator rather than hiding the race. Display whatever is available (candidate names, party, race title) and surface the best available external source.

**Data source research for local races (post-MVP):**
- **Florida Division of Elections** (dos.myflorida.com/elections) — candidate filings for ALL races including local. Has name, party, district, contact. No positions.
- **VoteSmart** — covers some county-level races, has issue positions and ratings from advocacy groups
- **League of Women Voters Florida** (lwvfl.org) — publishes candidate questionnaires for local races in many counties. Structured data, neutral source.
- **Local newspapers** — Miami Herald, Tampa Bay Times, Orlando Sentinel all publish voter guides. Scrapeable but inconsistent structure.
- **BallotReady** (ballotready.org) — commercial service specifically focused on down-ballot races. Has an API. Best single source for local race coverage. Worth evaluating for v2.
- **Open States** (openstates.org) — state legislative data including FL House/Senate. Good for state legislative races.

**MVP behavior for limited data:**
```
[Limited Data]  Miami-Dade School Board, District 3
Candidates: John Smith, Jane Doe
Source: Florida Division of Elections

We don't have detailed candidate information for this race yet.
View the official candidate list → [FL Division of Elections link]
Check the League of Women Voters guide → [LWV FL link]
```

### 5. Language Support — Architecture for Multi-Language, English MVP ✅
- UI strings externalized to i18n JSON files from day one (`/locales/en.json`)
- No hardcoded UI strings in components — all text via translation keys
- Claude handles multi-language natively — the agent prompt will specify response language based on `session.language` field (defaults to `"en"`)
- Database: all LLM-generated content (summaries, arguments) stored with a `language` field. If a Spanish user requests a guide, summaries are generated in Spanish and cached separately — not translated from English post-hoc.
- URL structure supports locale: `/es/` prefix for future Spanish version
- **MVP ships English only.** Spanish (and potentially Haitian Creole, given Florida demographics) in v2.
- `sessions` table has `language` field defaulting to `"en"`. Detection logic (from browser `Accept-Language` header) is wired but not acted on in MVP — just logged for v2 planning.
