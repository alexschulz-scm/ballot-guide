# Build Prompt: [Component Name]

**Component:** `[directory/path/]`  
**Spec:** `docs/specs/spec-[component].md`  
**Estimated sessions:** [N] focused sessions  

---

## ⚠️ Before Anything Else

Read these files in order before responding:
1. `CLAUDE.md` (repo root)
2. `docs/specs/spec-[component].md`

Do not write any code until instructed. Confirm you have read both files by summarizing in 3 bullet points what this component does and what its most important constraints are.

---

## PHASE 1 — PLANNING

*Goal: produce a reviewed implementation plan before touching any code.*  
*This phase runs in chat (Claude.ai or Claude Code). No implementation.*

### Planning Instructions

**Step 1: Summarize the component**  
In your own words (3-5 sentences), explain what this component does, why it exists, and what depends on it. If anything in the spec is unclear, ask now — not during implementation.

**Step 2: Identify the build order**  
List every file you will create, in the exact order you will create them. Justify the order. Dependencies must be built before the things that depend on them.

**Step 3: List dependencies and risks**  
For each external dependency:
- What happens if it's unavailable during development?
- What mock/stub will you use in tests?
- What is the fallback behavior at runtime?

**Step 4: Confirm constraints**  
List the 5 most important constraints from the spec's "Known Constraints" section. For each one, describe exactly how you will enforce it in code.

**Step 5: Flag ambiguities**  
List questions or ambiguities that could affect implementation. Do not assume answers — list them explicitly for human review.

### ✋ STOP HERE  
Do not proceed to Phase 2 until the plan is reviewed and approved by the human.

---

## PHASE 2 — BUILD

*Execute in Claude Code (VS Code) after plan approval.*  
*Complete tasks in order. Do not skip. Do not combine tasks.*  
*Run tests after each session before proceeding to the next.*

---

### Session [A]: [Name]

**Goal:** [What this session produces.]  
**Depends on:** [Prior sessions or components.]

#### Task [A1]: [Name]

**Create:** `[filepath]`  
**Purpose:** [One sentence.]

**Must implement:**
[Specific functions, classes, or behaviors. Be explicit. Cheap models need exact specifications.]

**Must NOT:**
[Specific anti-patterns to avoid for this task.]

**Acceptance check:**
```python
# Paste-able code the agent runs to verify this task is done
```

---

#### Task [A2]: Tests for Session A

**Create:** `tests/[component]/test_[component].py`

**Required test cases:**
```
test_[scenario_1]
test_[scenario_2]
test_[error_case_1]
...
```

Run: `pytest tests/[component]/ -v`  
All must pass before proceeding.

---

### Session [B]: [Name]

[Repeat session structure]

---

## Final Verification

```bash
pytest tests/[component]/ -v --tb=short
```

Run the Definition of Done checklist from `docs/specs/spec-[component].md` section 8.  
Do not mark this component complete until every box is checked.

---

## If You Get Stuck

**"The spec is ambiguous about X"**  
→ Stop. Describe the ambiguity and two reasonable interpretations. Wait for human decision.

**"I can't find the right library / API format"**  
→ Use a mock/fixture. Flag for human to validate. Do not guess.

**"Tests are failing"**  
→ Do not rewrite tests to make them pass. Add print statements to isolate. Fix the code.

**"Context is getting long and I'm losing track"**  
→ Stop. Write: "Here is what I've built. Here is what remains. Here are open questions." Then continue.

**"I think there's a better way to do this than the spec says"**  
→ Flag it. Describe the spec approach and your proposed alternative. Wait for human decision. Do not silently deviate.
