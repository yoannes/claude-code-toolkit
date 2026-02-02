---
name: go
description: Fast autonomous execution with lightweight planning. Read-gated editing, task-agnostic. Use when asked for "/go", "just go", "go fast", "quick fix", or "quick build".
---

# /go — Fast Autonomous Execution

Execute tasks directly. No multi-agent planning, no EnterPlanMode ceremony.

**DO NOT** use EnterPlanMode or launch planning agents. This is /go, not /melt.

## How It Works

1. **Read-gate** — You must read at least one relevant file before editing. The hook blocks Edit/Write until you've used Read, Grep, or Glob. This resets per task.
2. **Execute** — Make changes. Run linters if you changed code.
3. **Ship** — Commit and push.
4. **Checkpoint** — Write a lightweight 3+1 checkpoint and stop.

```
ACTIVATE → READ (gate unlocks) → EXECUTE → SHIP → CHECKPOINT → STOP
```

## Task-Agnostic

/go works for any task type:

| Type | Example | Verification |
|------|---------|-------------|
| Code | Fix bug, add feature | Run linter |
| Docs | Update README, add guide | Read the output |
| Config | Change settings, env vars | Validate syntax |
| Research | Answer a question | Summarize findings |

Don't force code-specific steps on non-code tasks.

## Before You Edit, Ask Yourself

> "How will I know this worked?"

Name your verification method before starting. This is not enforced by hooks — it's your professional responsibility. For code: run the linter. For docs: re-read the changed section. For config: validate the format. For research: check your sources.

## Checkpoint (3+1 Fields)

Before stopping, write `.claude/completion-checkpoint.json`:

```json
{
  "self_report": {
    "is_job_complete": true,
    "code_changes_made": false
  },
  "reflection": {
    "what_was_done": "Description of what was done (>20 chars)",
    "what_remains": "none"
  }
}
```

**When `code_changes_made` is true, add:**
```json
{
  "self_report": {
    "is_job_complete": true,
    "code_changes_made": true,
    "linters_pass": true
  },
  "reflection": {
    "what_was_done": "Fixed the auth timeout by increasing retry limit in api-client.ts",
    "what_remains": "none"
  }
}
```

**Rules:**
- `what_was_done` must be >20 characters
- `what_remains` must be empty ("none") to stop
- `linters_pass` only required when `code_changes_made` is true
- `code_changes_made` is your self-report, not git diff detection

## When to Use /go vs /melt

| /go | /melt |
|-----|-------|
| Clear task, bounded scope | Ambiguous problem, needs exploration |
| Any complexity if you're confident | Multi-stakeholder architectural decisions |
| Speed matters | Thoroughness matters |

## Triggers

- `/go` (primary)
- "just go", "go fast", "quick fix", "quick build"
