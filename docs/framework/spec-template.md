# Spec: [Component Name]

**Status:** Draft | Review | Approved  
**Version:** 1.0  
**Component:** `[directory/path/]`  
**Depends on:** `[other specs or docs this builds on]`  
**Consumed by:** `[what reads/calls this component]`  
**Last updated:** YYYY-MM-DD

---

## 1. Overview

[2-3 sentences: what this component does, why it exists, what problem it solves.]

### What this component is NOT responsible for
[Explicit boundary definition. What a reader might expect this to do that it doesn't.]

---

## 2. Shared Principles

[Any non-negotiable rules that apply to everything in this component. Reference CLAUDE.md for project-wide rules — only add component-specific rules here.]

---

## 3. Interfaces

[For each tool/endpoint/function: input schema, output schema, error codes.]

### 3.x [Tool / Endpoint / Function Name]

**Purpose:** [One sentence.]

**Input schema:**
```python
class XInput(BaseModel):
    field: type    # description
```

**Output schema:**
```python
class XOutput(BaseModel):
    field: type    # description
```

**Error codes:**
| Code | Recoverable | Meaning |
|------|-------------|---------|
| `ERROR_CODE` | true/false | What happened |

**Cache TTL:** [duration or N/A]  
**Cache key:** `[prefix:key_parts]`

---

## 4. Data Models

[Full Pydantic model definitions if not fully captured in section 3. Reference `shared/models.py` for shared types.]

---

## 5. Error Handling

[How errors flow through this component. What the caller can expect.]

---

## 6. File Structure

```
[component-directory]/
├── file.py    # purpose
└── ...
```

---

## 7. Acceptance Criteria

[Binary, testable, Given/When/Then format. Every behavior you care about.]

- [ ] **AC-[COMPONENT]-01:** Given [input/state] when [action] then [exact observable outcome]
- [ ] **AC-[COMPONENT]-02:** ...

---

## 8. Definition of Done

- [ ] All acceptance criteria pass
- [ ] Unit tests written AND passing
- [ ] Edge cases from spec covered by tests
- [ ] No hardcoded values (secrets, magic numbers, config)
- [ ] All errors return structured error objects (no raw exceptions)
- [ ] All functions have docstrings
- [ ] No TODOs in code (use `# FUTURE:` prefix)
- [ ] Runs in Docker Compose local dev
- [ ] No functions longer than 40 lines
- [ ] [Component-specific DoD items]

---

## 9. Test Strategy

### Test file locations
```
tests/[component]/
├── conftest.py
└── test_[component].py
```

### Test categories
[List test categories and what each covers: unit, integration, contract, error injection, etc.]

### Required test cases
```
test_[scenario]
test_[error_case]
...
```

### Bug-to-test learning loop
When a bug is found:
1. Write a failing test reproducing the bug before fixing
2. Fix code until test passes
3. Add scenario to error table in this spec if missing
4. Add guardrail to `CLAUDE.md` if it's a class of problem

---

## 10. Known Constraints (Agent Guardrails)

**DO NOT** [specific anti-pattern]  
**DO NOT** [specific anti-pattern]  
**ALWAYS** [specific required pattern]  

---

## 🎓 Learning Corner

### 🏗️ Architecture Thinking
[Why this component is designed the way it is. The tradeoffs. How to evaluate similar decisions on future projects.]

### 🤖 AI Engineering Concepts
[The AI-specific patterns at work here. Vocabulary and mental models for AI-native PMs and engineers.]

### 📦 PM/TPM Craft
[How this spec decision maps to PM/TPM skills in the AI era. Acceptance criteria, failure modes, scoping AI features, the agent-driven development workflow.]
