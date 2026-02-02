# Hook Scripts

This directory contains Python hook scripts that extend Claude Code's lifecycle events.

## Active Hooks (Configured in settings.json)

| Script | Event | Purpose |
|--------|-------|---------|
| `auto-update.py` | SessionStart | Auto-updates toolkit from GitHub on session start |
| `session-snapshot.py` | SessionStart | Captures git diff hash at session start for change tracking |
| `compound-context-loader.py` | SessionStart | Injects top-5 relevant memory events at session start |
| `read-docs-reminder.py` | SessionStart | Reminds to read project documentation on new sessions |
| `skill-state-initializer.py` | UserPromptSubmit | Creates state files for /melt and /appfix to enable auto-approval |
| `read-docs-trigger.py` | UserPromptSubmit | Suggests reading docs when "read the docs" appears in prompt |
| `pretooluse-auto-approve.py` | PreToolUse (*) | Auto-approves ALL tools during autonomous mode |
| `plan-mode-enforcer.py` | PreToolUse (Edit/Write) | Blocks Edit/Write until plan mode completed + /go Read-gate |
| `deploy-enforcer.py` | PreToolUse (Bash) | Blocks subagent deploys and production deploys |
| `azure-command-guard.sh` | PreToolUse (Bash) | Blocks dangerous Azure CLI commands |
| `exa-search-enforcer.py` | PreToolUse (WebSearch) | Blocks WebSearch, redirects to Exa MCP |
| `lite-heavy-enforcer.py` | PreToolUse (ExitPlanMode) | Blocks ExitPlanMode until Lite Heavy agents launched |
| `checkpoint-invalidator.py` | PostToolUse (Edit/Write) | Resets stale checkpoint flags when code changes |
| `lite-heavy-tracker.py` | PostToolUse (Read/Task) | Tracks Lite Heavy agent progress |
| `go-context-tracker.py` | PostToolUse (Read/Grep/Glob) | Tracks context gathering for /go Read-gate |
| `memory-recall.py` | PostToolUse (Read/Grep/Glob) | Mid-session memory retrieval (8 recalls/session) |
| `bash-version-tracker.py` | PostToolUse (Bash) | Tracks version after git commits, updates checkpoint |
| `doc-updater-async.py` | PostToolUse (Bash) | Suggests async doc updates after git commits |
| `plan-mode-tracker.py` | PostToolUse (ExitPlanMode) | Marks plan_mode_completed=true in state file |
| `plan-execution-reminder.py` | PostToolUse (ExitPlanMode) | Injects autonomous execution context after plan approval |
| `skill-continuation-reminder.py` | PostToolUse (Skill) | Continues autonomous loop after skill delegation |
| `stop-validator.py` | Stop | Validates completion checkpoint before allowing session end |
| `precompact-capture.py` | PreCompact | Injects session summary before context compaction |
| `permissionrequest-auto-approve.py` | PermissionRequest | Fallback auto-approve during autonomous mode |

## Internal Modules (Not Lifecycle Hooks)

| Module | Purpose |
|--------|---------|
| `_common.py` | Shared utility functions (state detection, version tracking, logging) |
| `_memory.py` | Memory primitives (event store, entity matching, crash-safe writes) |
| `_state.py` | State file management for autonomous modes |
| `_checkpoint.py` | Checkpoint operations (load, save, invalidation) |
| `_sv_validators.py` | Validation logic for stop-validator (sub-validators) |
| `_sv_templates.py` | Blocking message templates for stop-validator |

## Utility Scripts (Not Lifecycle Hooks)

| Script | Purpose |
|--------|---------|
| `surf-verify.py` | Runs Surf CLI for browser verification, generates web-smoke artifacts |
| `worktree-manager.py` | Creates/manages git worktrees for parallel agent isolation |
| `cleanup.py` | Reclaim disk space from Claude Code session data |
| `deploy-verify.py` | Deployment verification |

### _common.py Functions

```python
# State detection
is_melt_active(cwd)             # Check if .claude/melt-state.json exists
is_appfix_active(cwd)           # Check if .claude/appfix-state.json exists
is_autonomous_mode_active(cwd)  # Check if either melt or appfix is active

# Version tracking (excludes infrastructure paths from dirty check)
get_code_version(cwd)           # Returns "abc1234" or "abc1234-dirty" (stable during edits)
get_diff_hash(cwd)              # Returns 12-char hash of current diff

# Debugging
log_debug(message, cwd)         # Write debug logs to temp dir

# Shared constants
VERSION_TRACKING_EXCLUSIONS     # Git pathspecs excluding .claude/, locks, etc.
```

### Infrastructure Path Exclusions

The `stop-validator.py` and related hooks exclude these paths from deployment/linting requirements:

```python
infrastructure_patterns = [
    'config/hooks/',      # Hook scripts
    'config/skills/',     # Skill definitions
    'config/commands/',   # Command definitions
    '.claude/',           # State and checkpoint files
    'prompts/config/',    # Toolkit configuration
    'prompts/scripts/',   # Documentation utilities
    'scripts/',           # Project scripts
]
```

Changes to these paths are treated as "infrastructure changes" and don't require deployment, linting, or browser testing.

## Security Model

Auto-approval hooks only activate when a state file exists:
- `.claude/melt-state.json` - Created by `/melt` skill
- `.claude/appfix-state.json` - Created by `/appfix` skill

Normal sessions without these files require user approval for all tool operations.

## Hook Execution Flow

```
SessionStart
    └─► auto-update.py (updates toolkit from GitHub)
    └─► session-snapshot.py (captures git hash)
    └─► compound-context-loader.py (injects memory events)
    └─► read-docs-reminder.py (reminds to read docs)

UserPromptSubmit
    └─► skill-state-initializer.py (creates melt/appfix state files)
    └─► read-docs-trigger.py (checks for "read the docs")

PreToolUse (*)
    └─► pretooluse-auto-approve.py (auto-approve if autonomous mode active)

PreToolUse (Edit/Write)
    └─► plan-mode-enforcer.py (blocks until plan mode completed, iteration 1 only)

PreToolUse (Bash)
    └─► deploy-enforcer.py (blocks subagent/production deploys)
    └─► azure-command-guard.sh (blocks dangerous az commands)

PreToolUse (WebSearch)
    └─► exa-search-enforcer.py (blocks WebSearch, redirects to Exa MCP)

PreToolUse (ExitPlanMode)
    └─► lite-heavy-enforcer.py (blocks until Lite Heavy agents launched)

PostToolUse (Edit/Write)
    └─► checkpoint-invalidator.py (resets stale checkpoint)

PostToolUse (Read/Grep/Glob)
    └─► go-context-tracker.py (tracks /go Read-gate)
    └─► memory-recall.py (mid-session memory retrieval)

PostToolUse (Read/Task)
    └─► lite-heavy-tracker.py (tracks Lite Heavy progress)

PostToolUse (Bash)
    └─► bash-version-tracker.py (tracks version after git commits)
    └─► doc-updater-async.py (suggests doc updates)

PostToolUse (ExitPlanMode)
    └─► plan-execution-reminder.py (injects context)
    └─► plan-mode-tracker.py (marks plan_mode_completed=true)

PostToolUse (Skill)
    └─► skill-continuation-reminder.py (continues autonomous loop)

Stop
    └─► stop-validator.py (validates checkpoint + auto-captures memory event)

PreCompact
    └─► precompact-capture.py (injects session summary)

PermissionRequest (any tool)
    └─► permissionrequest-auto-approve.py (fallback auto-approve if autonomous)
```

## Testing

Three levels of tests verify hook behavior:

```bash
# Level 1: Pytest subprocess tests (fast, no API cost)
cd prompts && python3 -m pytest config/hooks/tests/test_plan_mode_hooks.py -v

# Level 2: Claude headless E2E (real sessions, ~$0.05-0.15)
cd prompts && bash scripts/test-e2e-headless.sh

# Level 3: tmux interactive E2E (manual observation)
cd prompts && bash scripts/test-e2e-tmux.sh --observe
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_plan_mode_hooks.py` | 24 | Enforcer, tracker, initializer, full chain |
| `tests/test_sv_validators.py` | — | Stop-validator sub-validators |
| `tests/test_memory_system.py` | — | Memory system primitives |
| `scripts/test-e2e-headless.sh` | 5 | Real Claude sessions via `claude -p` |
| `scripts/test-e2e-tmux.sh` | 3 | Interactive sessions with tmux |

## Related Documentation

- [Hook System Deep Dive](../../docs/concepts/hooks.md)
- [Settings Reference](../../docs/reference/settings.md)
- [Appfix Guide](../../docs/skills/appfix-guide.md)
