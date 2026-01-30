# /godo - Task-Agnostic Autonomous Execution

Complete guide to the `/godo` skill for autonomous task execution with completion validation.

## Table of Contents

1. [Overview](#overview)
2. [When to Use](#when-to-use)
3. [Workflow](#workflow)
4. [Completion Checkpoint](#completion-checkpoint)
5. [Comparison with /appfix](#comparison-with-appfix)
6. [Troubleshooting](#troubleshooting)

---

## Overview

`/godo` is the universal autonomous execution skill. It provides:

- **100% Autonomous Operation** - No permission prompts, no confirmation requests
- **Completion Checkpoint** - Deterministic boolean validation before stopping
- **Browser Verification** - Mandatory testing in real browser
- **Strict Linter Policy** - Fix ALL errors, including pre-existing ones

### Key Features

| Feature | Description |
|---------|-------------|
| Auto-approval hooks | All tool permissions granted automatically |
| Stop hook validation | Cannot stop until checkpoint booleans pass |
| Checkpoint invalidation | Stale fields reset when code changes |
| Version tracking | Detects code drift since checkpoints were set |

---

## When to Use

### Use /godo

| Scenario | Example |
|----------|---------|
| Feature implementation | "Add a logout button to the navbar" |
| Bug fixes | "Fix the broken pagination" |
| Refactoring | "Convert class components to hooks" |
| Config changes | "Update the API endpoint URLs" |
| Any task requiring completion verification | "Deploy the new feature" |

### Use /appfix Instead

| Scenario | Why appfix? |
|----------|-------------|
| Production/staging is down | Adds health check phases |
| Debugging failures | Adds log collection phases |
| Diagnosing errors | Requires service topology |

---

## Workflow

### Phase 0: Activation

```bash
# Create state file IMMEDIATELY (enables auto-approval)
mkdir -p .claude && cat > .claude/godo-state.json << 'EOF'
{"started_at": "2025-01-26T10:00:00Z", "task": "user task"}
EOF

# Also create user-level state for cross-repo work
mkdir -p ~/.claude && cat > ~/.claude/godo-state.json << 'EOF'
{"started_at": "2025-01-26T10:00:00Z", "origin_project": "/path/to/project"}
EOF
```

### Phase 0.5: Codebase Context (MANDATORY)

**This phase is required before making any changes.**

1. `EnterPlanMode` - Switch to planning mode
2. **Explore the codebase**:
   - Project structure and architecture
   - Recent commits: `git log --oneline -15`
   - Environment and deployment configs
   - Relevant code patterns for the task
   - Existing tests and validation
3. **Write to plan file**:
   - What you understand about the codebase
   - How the task fits into existing architecture
   - Implementation approach with specific files
   - Potential risks or dependencies
4. `ExitPlanMode` - Get plan approved

**Why this matters**: Jumping straight to code leads to broken functionality, inconsistent patterns, and wasted effort.

### Phase 1: Execute

1. Make code changes (Edit tool)
2. Run linters, fix ALL errors
3. Commit and push
4. Deploy if needed

### Phase 2: Verify (MANDATORY)

**CRITICAL: Use Surf CLI first, not Chrome MCP.**

1. Run Surf CLI: `python3 ~/.claude/hooks/surf-verify.py --urls "https://..."`
2. Check `.claude/web-smoke/summary.json` for pass/fail
3. Only fall back to Chrome MCP if Surf CLI unavailable
4. Check console for errors
5. Verify feature works as expected

### Phase 3: Complete

1. Update completion checkpoint
2. Try to stop
3. If blocked: address issues, try again
4. If passed: clean up state files

---

## Completion Checkpoint

Create `.claude/completion-checkpoint.json`:

```json
{
  "self_report": {
    "code_changes_made": true,
    "web_testing_done": true,
    "web_testing_done_at_version": "abc1234",
    "deployed": true,
    "deployed_at_version": "abc1234",
    "console_errors_checked": true,
    "console_errors_checked_at_version": "abc1234",
    "linters_pass": true,
    "linters_pass_at_version": "abc1234",
    "preexisting_issues_fixed": true,
    "is_job_complete": true
  },
  "reflection": {
    "what_was_done": "Implemented feature X",
    "what_remains": "none"
  },
  "evidence": {
    "urls_tested": ["https://staging.example.com/feature"],
    "console_clean": true
  }
}
```

### Required Fields

| Field | When Required | Meaning |
|-------|---------------|---------|
| `is_job_complete` | Always | Is the task fully done? |
| `web_testing_done` | Always | Did you verify in browser? |
| `code_changes_made` | Always | Did you modify code? |
| `deployed` | If code changed | Did you deploy? |
| `linters_pass` | If code changed | Do all linters pass? |
| `console_errors_checked` | Always | Did you check console? |
| `what_remains` | Always | Must be "none" or empty |

### Version Tracking

Version-dependent fields include `*_at_version` to detect staleness:

```
deployed: true
deployed_at_version: "abc1234"

# If code changes to "def5678", deployed becomes STALE
# Must re-deploy and update version
```

---

## Comparison with /appfix

| Aspect | /godo | /appfix |
|--------|-------|---------|
| **Purpose** | Any task | Debugging failures |
| **docs_read_at_start** | Not required | Required |
| **Health check phase** | No | Yes |
| **Log collection** | No | Yes |
| **Service topology** | Not required | Required |
| **Linter policy** | Strict | Strict |
| **Browser verification** | Required | Required |
| **Checkpoint schema** | Same | Same |

`/godo` is the universal base. `/appfix` adds debugging-specific phases.

---

## Troubleshooting

### "Checkpoint validation failed"

Your checkpoint has incomplete booleans. Check:
1. `is_job_complete` - Are you honestly done?
2. `web_testing_done` - Did you verify in browser?
3. `linters_pass` - Did all linters pass?
4. `what_remains` - Is it empty?

### "Stop hook blocked me"

This is expected when work is incomplete:
- If `is_job_complete: false` → you're blocked
- Complete the work, update checkpoint, try again

### "Field is STALE"

A checkpoint was set at an older code version:
1. Re-run that step with current code
2. Get current version: `git rev-parse --short HEAD`
3. Update checkpoint with new version

### "linters_pass is false"

Fix ALL linter errors:
```bash
# JavaScript/TypeScript
npm run lint && npx tsc --noEmit

# Python
ruff check --fix . && pyright
```

**"These errors aren't related to our code" is NOT acceptable.**

---

## State Files

| File | Purpose |
|------|---------|
| `.claude/godo-state.json` | Enables auto-approval hooks |
| `.claude/completion-checkpoint.json` | Boolean self-report for validation |
| `~/.claude/godo-state.json` | User-level state for cross-repo work |

### Cleanup

Remove state files when done:
```bash
rm -f ~/.claude/godo-state.json .claude/godo-state.json
```
