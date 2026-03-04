# Framework Learnings

This is the living log of what works, what doesn't, and what changed — and why. Dated entries. Honest observations. This file makes the framework better over time.

**How to add an entry:**
When something surprises you (good or bad), add it here. Include: what happened, why it happened, and what changed in the framework as a result.

---

## Format

```
### YYYY-MM-DD — [Short title]
**What happened:** ...
**Why:** ...
**What changed:** [spec template / prompt template / CLAUDE.md / nothing yet]
**Confidence:** Low | Medium | High  (how sure are you this generalizes?)
```

---

## Entries

### 2026-02-28 — Framework initialized from Ballot Guide project

**What happened:** Framework templates (spec, prompt, CLAUDE.md) created as a byproduct of building the Ballot Guide MVP. Not yet battle-tested — this is the baseline.

**Why:** Better to start with a real project's patterns than design a framework in the abstract.

**What changed:** Initial templates created.

**Confidence:** Low — these are hypotheses, not validated patterns yet.

---

### [Date] — [Your first real learning goes here]

Add entries as you build. Some things to watch for:

- Did the agent misunderstand a spec section? → The spec was ambiguous. How do you write it differently next time?
- Did a test catch a real bug? → What kind of test was it? Add to "test categories that pay off" below.
- Did the agent do something useful you didn't ask for? → Note it. Maybe it should be in the template.
- Did you have to restart a session because context got corrupted? → What was the trigger? Add a checkpoint rule.
- Did a cheap model fail where a frontier model would have succeeded? → Was it a prompt problem or a genuine capability gap?

---

## Patterns (updated as entries accumulate)

### Test categories that consistently catch real bugs
[Fill in as you learn]

### Spec sections that agents most often misinterpret
[Fill in as you learn]

### Prompt patterns that work well with cheap models
[Fill in as you learn]

### Context window failure modes
[Fill in as you learn]

### Guardrails that prevented real problems
[Fill in as you learn]
