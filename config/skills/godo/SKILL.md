---
name: godo
description: Task-agnostic autonomous execution. Identifies any task and executes it through a complete fix-verify loop until done. Use when asked to "go do", "just do it", "execute this", or "/godo".
---

# Autonomous Task Execution (/godo)

Task-agnostic autonomous execution skill that iterates until the task is complete and verified.

## Architecture: Completion Checkpoint

This workflow uses a **deterministic boolean checkpoint** to enforce completion:

```
┌─────────────────────────────────────────────────────────────────┐
│  STOP HOOK VALIDATION                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Load .claude/completion-checkpoint.json                         │
│                                                                  │
│  Check booleans deterministically:                               │
│    - is_job_complete: false → BLOCKED                            │
│    - web_testing_done: false → BLOCKED                           │
│    - deployed: false (if code changed) → BLOCKED                 │
│    - linters_pass: false (if code changed) → BLOCKED             │
│    - what_remains not empty → BLOCKED                            │
│                                                                  │
│  If blocked → stderr: continuation instructions                  │
│  All checks pass → exit(0) → Allow stop                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## CRITICAL: Autonomous Execution

**THIS WORKFLOW IS 100% AUTONOMOUS. YOU MUST:**

1. **NEVER ask for confirmation** - No "Should I commit?", "Should I deploy?"
2. **Auto-commit and push** - When changes are made, commit and push immediately
3. **Auto-deploy** - Trigger deployments without asking
4. **Complete verification** - Test in browser and check console
5. **Fill out checkpoint honestly** - The stop hook checks your booleans

**Only stop when the checkpoint can pass. If your booleans say the job isn't done, you'll be blocked.**

### Credentials Exception

If credentials are missing (API keys, test credentials), ask the user **once at start**. After that, proceed autonomously.

## Browser Verification is MANDATORY

**ALL godo sessions require browser verification. No exceptions.**

| Task Type | Browser Verification Purpose |
|-----------|------------------------------|
| Feature implementation | Verify feature works in UI |
| Bug fix | Verify bug is fixed |
| Refactoring | Verify app still works |
| Config changes | Verify behavior changed |
| API changes | Verify frontend integration works |

**The purpose of browser verification is to confirm the application works after your changes.**

## Triggers

- `/godo`
- "go do"
- "just do it"
- "execute this"
- "make it happen"

## Completion Checkpoint Schema

Before stopping, you MUST create `.claude/completion-checkpoint.json`:

```json
{
  "self_report": {
    "code_changes_made": true,
    "web_testing_done": true,
    "web_testing_done_at_version": "abc1234",
    "api_testing_done": true,
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
    "what_was_done": "Implemented feature X, deployed to staging, verified in browser",
    "what_remains": "none",
    "blockers": null
  },
  "evidence": {
    "urls_tested": ["https://staging.example.com/feature"],
    "console_clean": true
  }
}
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `code_changes_made` | bool | yes | Were any code files modified? |
| `web_testing_done` | bool | yes | Did you verify in a real browser? |
| `deployed` | bool | conditional | Did you deploy the changes? |
| `console_errors_checked` | bool | yes | Did you check browser console? |
| `linters_pass` | bool | if code changed | Did all linters pass with zero errors? |
| `preexisting_issues_fixed` | bool | if code changed | Did you fix ALL issues (no excuses)? |
| `is_job_complete` | bool | yes | **Critical** - Is the job ACTUALLY done? |
| `what_remains` | string | yes | Must be "none" to allow stop |

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0: ACTIVATION                                            │
│     └─► Create .claude/godo-state.json (enables auto-approval)  │
│     └─► Identify task from user prompt                          │
├─────────────────────────────────────────────────────────────────┤
│  ╔═══════════════════════════════════════════════════════════╗  │
│  ║  PHASE 0.5: CODEBASE CONTEXT (MANDATORY)                  ║  │
│  ║     └─► EnterPlanMode                                     ║  │
│  ║     └─► Explore: architecture, recent commits, configs    ║  │
│  ║     └─► Write understanding + implementation plan         ║  │
│  ║     └─► ExitPlanMode                                      ║  │
│  ╚═══════════════════════════════════════════════════════════╝  │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 1: EXECUTE                                               │
│     └─► Make code changes                                       │
│     └─► Run linters, fix ALL errors                             │
│     └─► Commit and push                                         │
│     └─► Deploy                                                  │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 2: VERIFY (MANDATORY - Surf CLI first!)                  │
│     └─► Run: python3 ~/.claude/hooks/surf-verify.py             │
│     └─► Check .claude/web-smoke/summary.json passed             │
│     └─► Update completion checkpoint                            │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 3: COMPLETE                                              │
│     └─► Stop hook validates checkpoint                          │
│     └─► If blocked: continue working                            │
│     └─► If passed: clean up state files, done                   │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 0: Activation

**CRITICAL: Create state file FIRST to enable auto-approval.**

```bash
# Create state file IMMEDIATELY (enables auto-approval hooks)
mkdir -p .claude && cat > .claude/godo-state.json << 'EOF'
{
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "task": "user's task description"
}
EOF

# Also create user-level state for cross-repo work
mkdir -p ~/.claude && cat > ~/.claude/godo-state.json << 'EOF'
{
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "origin_project": "$(pwd)"
}
EOF
```

## Phase 0.5: Codebase Context (MANDATORY)

**This phase is REQUIRED before making any changes. Understanding the codebase prevents breaking changes and wasted effort.**

1. **Call `EnterPlanMode`**

2. **Explore the codebase**:
   - Project structure and architecture
   - Recent commits: `git log --oneline -15`
   - Environment and deployment configs
   - Relevant code patterns for the task
   - Existing tests and validation

3. **Write to plan file**:
   - What you understand about the codebase
   - How the task fits into existing architecture
   - Implementation approach with specific files to modify
   - Potential risks or dependencies

4. **Call `ExitPlanMode`**

**Why this matters:** Jumping straight to code without understanding the codebase leads to:
- Breaking existing functionality
- Inconsistent patterns
- Wasted effort on wrong approaches
- Missing edge cases

## Phase 1: Execute

### 1.1 Make Code Changes
Use Edit tool for targeted changes. Keep changes focused on the task.

### 1.2 Linter Verification (MANDATORY)

**STRICT POLICY: Fix ALL linter errors, including pre-existing ones.**

```bash
# JavaScript/TypeScript projects
[ -f package.json ] && npm run lint 2>/dev/null || npx eslint . --ext .js,.jsx,.ts,.tsx
[ -f tsconfig.json ] && npx tsc --noEmit

# Python projects
[ -f pyproject.toml ] && ruff check --fix .
[ -f pyrightconfig.json ] && pyright
```

**PROHIBITED EXCUSES:**
- "These errors aren't related to our code"
- "This was broken before we started"
- "I'll fix this in a separate PR"

### 1.3 Commit and Push
```bash
git add <specific files> && git commit -m "feat: [description]"
git push
```

### 1.4 Deploy
```bash
gh workflow run deploy.yml -f environment=staging
gh run watch --exit-status
```

## Phase 2: Verification (MANDATORY)

### CRITICAL: Use Surf CLI First, Not Chrome MCP

**DO NOT call Chrome MCP tools (mcp__claude-in-chrome__*) for verification.**

Your FIRST action in Phase 2 MUST be running Surf CLI:

```bash
# Step 1: ALWAYS try Surf CLI first
which surf && echo "Surf available" || echo "FALLBACK needed"

# Step 2: Run verification (creates artifacts automatically)
python3 ~/.claude/hooks/surf-verify.py --urls "https://staging.example.com/feature"

# Step 3: Check artifacts exist
cat .claude/web-smoke/summary.json
```

```
CORRECT:
1. Run surf-verify.py first
2. Only if Surf fails → Fall back to Chrome MCP

WRONG:
- Calling mcp__claude-in-chrome__tabs_context as first step
- Using Chrome MCP "because it's easier"
- Skipping Surf without trying it
```

### Fallback: Chrome MCP (ONLY if Surf CLI unavailable)

**Only use Chrome MCP if Surf CLI is not installed or surf-verify.py fails.**

```
- mcp__claude-in-chrome__navigate to the app URL
- mcp__claude-in-chrome__computer action=screenshot
- mcp__claude-in-chrome__read_console_messages
```

When using Chrome MCP fallback, you MUST manually create `.claude/web-smoke/summary.json`.

### Verification Checklist
- [ ] Surf CLI tried first (or documented why not)
- [ ] Navigate to actual app (not just /health)
- [ ] Screenshot captured showing feature works
- [ ] Console has ZERO errors
- [ ] Data actually displays (not spinner)

## Phase 3: Complete

Update checkpoint and try to stop. If blocked, address the issues and try again.

```json
{
  "self_report": {
    "code_changes_made": true,
    "web_testing_done": true,
    "web_testing_done_at_version": "abc1234",
    "deployed": true,
    "deployed_at_version": "abc1234",
    "console_errors_checked": true,
    "linters_pass": true,
    "linters_pass_at_version": "abc1234",
    "preexisting_issues_fixed": true,
    "is_job_complete": true
  },
  "reflection": {
    "what_was_done": "...",
    "what_remains": "none"
  },
  "evidence": {
    "urls_tested": ["https://..."],
    "console_clean": true
  }
}
```

**Cleanup on completion**: Remove state files when done:
```bash
rm -f ~/.claude/godo-state.json .claude/godo-state.json
```

## Exit Conditions

### Success (Checkpoint Passes)
- All self_report booleans are true (where required)
- what_remains is "none" or empty
- is_job_complete is true

### Blocked (Continue Working)
- Any required boolean is false
- what_remains lists incomplete work
- is_job_complete is false

### Blocked (Ask User)
- Missing credentials (once at start)
- Ambiguous destructive action
- Genuinely unclear requirements

## Comparison with /appfix

| Aspect | /godo | /appfix |
|--------|-------|---------|
| Purpose | Any task | Debugging failures |
| docs_read_at_start | Not required | Required |
| Health check phase | No | Yes |
| Log collection phase | No | Yes |
| Service topology | Not required | Required |
| Linter policy | Strict | Strict |
| Browser verification | Required | Required |
| Completion checkpoint | Same schema | Same schema |

`/godo` is the universal base skill. `/appfix` is a debugging specialization that adds diagnostic phases.

## Philosophy: Honest Self-Reflection

This system works because:

1. **Booleans force honesty** - You must choose true/false, no middle ground
2. **Self-enforcing** - If you say false, you're blocked
3. **Deterministic** - No regex heuristics, just boolean checks
4. **Trusts the model** - Models don't want to lie when asked directly

The stop hook doesn't try to catch lies. It asks direct questions:
- "Did you test this in the browser?" → Answer honestly
- "Is the job actually complete?" → Answer honestly

If you answer `false`, you're blocked. If you answer `true` honestly, you're done.
