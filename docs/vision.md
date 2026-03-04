# Ballot Guide — Product Vision

## The Problem

Voting is hard — not because people don't care, but because ballots are complex. A typical Florida general election asks voters to make decisions on constitutional amendments written in dense legal language, judicial retention votes, local races with little coverage, and statewide offices where candidate positions are buried across dozens of sources. Most voters walk in underprepared or don't vote at all on down-ballot races.

Existing voter guides are either partisan (produced by advocacy groups) or generic (produced by newspapers or the state). None of them start from what the *voter* cares about.

## The Vision

An AI-powered ballot guide that brings clarity — not direction. The system surfaces factual, sourced information about ballot measures and candidates, filtered through the lens of what each voter says matters most to them.

The user tells the system what they care about — housing costs, education funding, public safety, tax policy, environmental protection. The system finds their exact ballot, explains everything on it, and surfaces the most relevant items first — without ever telling them how to vote.

**The core promise: personalized clarity, zero bias.**

## What It Is

- A conversational AI guide that understands your priorities and your ballot
- A structured, printable report summarizing every race and measure relevant to you
- A factual, source-cited reference that explains what proposed laws would actually do
- A tool that presents proponent and opponent arguments with equal rigor

## What It Is Not

- Not a voter guide that tells you who to vote for
- Not a partisan tool — it does not infer or assume political alignment from stated priorities
- Not an opinion platform — every claim is sourced and attributed
- Not a replacement for official sources — it links to them

## Target Users

**Primary:** Florida registered voters who want to be informed but don't have time to research every item on their ballot.

**Secondary:** Civic educators, libraries, and community organizations that help citizens navigate elections.

## Core Principles

**Factual accuracy above all.** Every summary is based on primary sources — official ballot text, fiscal analyses, candidate filings. No claims without citations.

**Structural neutrality.** The system is architecturally prevented from making endorsements. Output schemas have no recommendation field. Prompts are audited for editorial drift.

**Both sides, always.** For every contested measure, the strongest proponent and opponent arguments are presented with equal treatment — even when only one side is relevant to the user's stated priorities.

**Source transparency.** Users can see where every piece of information came from, including the political lean of news sources.

**No inferred values.** The system only uses priorities the user explicitly states. It does not infer political alignment from zip code, stated priorities, or conversation history.

## MVP Scope

- **State:** Florida
- **Election:** Florida 2026 General Election (with Florida 2022 General as historical test data)
- **Interface:** Web chat + structured ballot report
- **Deployment:** Local development + Azure Container Apps (scale to zero)

## Success Criteria for MVP

A user can enter their Florida address and describe what they care about in natural language, receive a personalized ballot guide within 60 seconds, understand what every major item on their ballot would actually do, and feel confident walking into the voting booth — regardless of their political views.
