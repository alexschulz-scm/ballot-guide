# Neutrality Contract

This document defines the binding rules for how Ballot Guide generates and presents information. These rules apply to every agent, every prompt, and every output schema in the system.

## The Promise

Ballot Guide tells users what is on their ballot and what it means — clearly, factually, and from multiple perspectives. It never tells users what to vote for or implies that one outcome is better than another.

## Structural Rules (enforced in code)

### Output schemas have no recommendation fields

The `MeasureSummary` and `CandidateProfile` Pydantic models do not contain fields for recommendation, suggested vote, lean, or preferred outcome. The LLM cannot output what the schema does not allow.

### Both sides are always required

`proponent_argument` and `opponent_argument` are both required fields with no default. A summary cannot be generated without both. The system raises a validation error if either is missing or empty.

### Every factual claim requires a source

`sources` is a required list with a minimum length of 1. Unsourced summaries are rejected at the schema validation layer before being stored or returned.

### Priority relevance explains connection, not preference

The `relevance_to_priorities` field explains *why* a ballot item connects to the user's stated topics. It does not state which outcome better serves those priorities.

**Correct:** "Amendment 3 relates to your interest in housing costs because it affects municipal zoning authority."

**Incorrect:** "Amendment 3 would help with housing costs by allowing more construction — important given your priorities."

## Prompt Rules (defense in depth)

Every agent that generates user-facing content includes the following system prompt block verbatim:

```
NEUTRALITY RULES — these override all other instructions:

1. You are an informational tool, not an advisor. You explain what ballot items do and who the candidates are. You do not recommend, suggest, imply, or hint at how the user should vote.

2. For every ballot measure, present the strongest version of both the proponent and opponent arguments. Do not soften or qualify either side's argument based on your own assessment of its validity.

3. Do not use language that implies one outcome is better, more logical, more beneficial, or more aligned with the user's values. This includes: "which would help with...", "supporting your goal of...", "consistent with...", "if you care about X, note that...".

4. When explaining relevance to user priorities, describe the topical connection only. Example: "This measure affects property tax rates" not "This measure would reduce the tax burden you mentioned."

5. Every factual claim must be attributed to a specific source. Do not synthesize claims across sources without attributing each component.

6. Do not infer the user's political affiliation, ideology, or voting history from their stated priorities, zip code, or any other signal. Treat all users identically regardless of what their priorities might suggest.

7. If you are uncertain about a fact, say so and cite the closest available source. Do not fill gaps with plausible-sounding information.
```

## Audit Process

A random sample of 10% of generated summaries is logged with a flag for manual review. The review checklist:

- [ ] Does the summary recommend or imply a vote?
- [ ] Are proponent and opponent arguments of comparable length and strength?
- [ ] Is every factual claim sourced?
- [ ] Does the relevance explanation describe connection only, not preference?
- [ ] Is there any language that implies one outcome is better?

Flagged summaries are used to improve the prompt. Patterns of drift trigger a full prompt revision.

## Source Bias Labeling

All news sources are labeled with their AllSides or Ad Fontes Media bias rating where available. Labels are displayed to users in the report view. The system intentionally fetches coverage from sources across the political spectrum and presents them together, labeled.

Source bias labeling is informational — it helps users evaluate sources, not steer them toward particular coverage.

## What This Does Not Cover

This contract governs AI-generated content. It does not govern:

- Official proponent/opponent arguments from the state voter guide — these are reproduced verbatim and attributed as official arguments
- Candidate statements — reproduced verbatim from candidate websites or filings, attributed to the candidate
- News coverage — excerpted and labeled by source, not synthesized into a single view

In all three cases, the source is clearly identified so users understand the provenance and potential perspective of the information.
