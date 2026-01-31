---
name: compound
description: Capture solved problems as structured markdown for cross-session learning. Use when you've solved a non-trivial problem and want future sessions to benefit. Triggers on "/compound", "document this solution", "capture this learning".
---

# Knowledge Capture (/compound)

Capture solved problems as structured markdown with YAML frontmatter. Creates searchable solution documents that future sessions can reference during planning.

## When to Use

- After debugging a non-trivial issue
- After discovering a platform-specific gotcha
- After finding a root cause that wasn't obvious
- After trying multiple approaches and finding one that works
- After making an architectural decision with rationale

**Quality gate**: This is manual trigger by design. Not every fix deserves permanent documentation. Use `/compound` when the learning would save time in future sessions.

## Triggers

- `/compound`
- "document this solution"
- "capture this learning"
- "remember this fix"

## Workflow

### Step 1: Extract Context from Current Session

Review the current session to identify:

1. **Problem**: What was broken or unclear?
2. **Symptoms**: What did the user or system observe?
3. **Investigation**: What did you try?
4. **What Didn't Work**: Failed approaches and why
5. **Root Cause**: The actual underlying issue
6. **Solution**: What fixed it
7. **Prevention**: How to avoid this in future

### Step 2: Classify with Schema

Read `~/.claude/skills/compound/references/solution-schema.md` for the controlled vocabulary.

Select:
- **problem_type**: One of 11 types (maps to category directory)
- **root_cause**: One of 16 causes
- **resolution_type**: One of 10 types
- **severity**: critical, high, medium, low
- **tags**: 3-7 searchable keywords

### Step 3: Generate File Path

```
docs/solutions/{category}/{slug}-{YYYYMMDD}.md
```

| problem_type | category directory |
|--------------|-------------------|
| build_error | build-errors |
| test_failure | test-failures |
| runtime_error | runtime-errors |
| performance_issue | performance |
| config_error | config-errors |
| dependency_issue | dependencies |
| integration_issue | integrations |
| logic_error | logic-errors |
| design_flaw | design-flaws |
| infrastructure_issue | infrastructure |
| security_issue | security |

**Slug format**: lowercase-hyphenated summary of the problem (max 50 chars)

### Step 4: Write Solution Document

```markdown
---
title: "{Concise problem description}"
date: {YYYY-MM-DD}
problem_type: {from schema}
component: "{file or module affected}"
root_cause: {from schema}
resolution_type: {from schema}
severity: {critical|high|medium|low}
symptoms:
  - "{Observable symptom 1}"
  - "{Observable symptom 2}"
tags: [{keyword1}, {keyword2}, {keyword3}]
---

# {Title}

## Problem

{1-3 sentences describing what was broken or unclear}

## Symptoms

- {What the user or system observed}
- {Error messages if any}
- {Unexpected behavior}

## What Didn't Work

**Attempt 1:** {What you tried}
- Why it failed: {Explanation}

**Attempt 2:** {What you tried}
- Why it failed: {Explanation}

## Root Cause

{2-5 sentences explaining the actual underlying issue}

## Solution

{Description of what fixed it}

```{language}
{Code snippet if applicable}
```

## Why This Works

{1-2 sentences explaining why this solution addresses the root cause}

## Prevention

- {How to avoid this in future}
- {Test or check that would catch this}
- {Documentation or comment that would help}

## Related

- {Link to related solution if any}
- {External documentation if relevant}
```

### Step 5: Confirm

After writing the file, confirm:

```
Solution captured: docs/solutions/{category}/{slug}-{date}.md

Tags: [{tags}]

Future sessions can find this via:
  grep -riwl "{keyword}" docs/solutions/
```

## Example Output

```markdown
---
title: "macOS ps returns different format than Linux"
date: 2026-01-30
problem_type: runtime_error
component: "config/hooks/_common.py"
root_cause: platform_difference
resolution_type: deletion
severity: high
symptoms:
  - "PID-scoped state files not found on macOS"
  - "Auto-approval hooks fail silently"
  - "Works on Linux, fails on macOS"
tags: [hooks, macos, pid, basename, platform, state-files]
---

# macOS ps returns different format than Linux

## Problem

PID-scoped state isolation silently failed on macOS because `_get_ancestor_pid()` used `basename` on paths that differ between platforms.

## Symptoms

- PID-scoped state files created but never found
- Auto-approval hooks didn't work on macOS
- Same code worked perfectly on Linux CI

## What Didn't Work

**Attempt 1:** Added fallback path for /proc/ not existing
- Why it failed: The `basename` call itself was the problem, not the path lookup

**Attempt 2:** Used psutil for cross-platform process info
- Why it failed: Violated the "no new dependencies" constraint

## Root Cause

`ps -o comm=` returns different formats:
- Linux: `/usr/bin/python3` (full path)
- macOS: `python3` (name only)

`basename()` on a name without path separators strips incorrectly.

## Solution

Deleted entire PID-scoping approach (473 lines). Replaced with session_id-based isolation via git worktrees.

## Why This Works

Session IDs are platform-independent strings. Git worktrees provide the isolation that PID-scoping was trying to achieve.

## Prevention

- Test hooks on both macOS and Linux before merging
- Process inspection APIs behave differently across platforms
- Prefer session_id isolation over PID-based isolation

## Related

- Git worktree implementation in worktree-manager.py
```

## Integration with /build

After Phase 3 (completion), if the task required debugging or non-trivial investigation:

> "If this fix was non-trivial, consider running `/compound` to capture the learning for future sessions."

This prompt is added to the stop-validator checklist to encourage adoption without forcing it.

## Retrieval

Future sessions find solutions via:

1. **SessionStart hook**: Injects recent + keyword-matched solutions
2. **Manual grep**: `grep -riwl "{keyword}" docs/solutions/`
3. **/build Phase 0.5**: Searches docs/solutions/ during planning

The YAML frontmatter enables structured queries:
```bash
# Find all high severity issues
grep -rl "severity: high" docs/solutions/

# Find all platform-related issues
grep -riwl "platform" docs/solutions/
```
