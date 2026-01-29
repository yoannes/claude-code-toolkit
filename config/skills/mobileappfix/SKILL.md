---
name: mobileappfix
description: Autonomous mobile app debugging using Maestro E2E tests. Mobile equivalent of /appfix.
---

# Autonomous Mobile App Debugging (/mobileappfix)

Autonomous debugging for React Native/Expo apps. Iterates until Maestro E2E tests pass.

> **Note**: `/mobileappfix` uses the same `appfix-state.json` as `/appfix`.
> For web applications, use `/appfix` instead.

## Triggers

- `/mobileappfix`
- "fix the mobile app"
- "Maestro tests failing"
- "app crashes on startup"

## CRITICAL: Autonomous Execution

**THIS WORKFLOW IS 100% AUTONOMOUS. YOU MUST:**

1. **NEVER ask for confirmation** - No "Should I rebuild?", "Should I commit?"
2. **Auto-commit and push** - When fixes are applied, commit immediately
3. **Auto-rebuild** - Trigger builds without asking
4. **Complete verification** - Run Maestro tests on simulator
5. **Fill out checkpoint honestly** - The stop hook checks your booleans

**Only stop when the checkpoint can pass.**

## Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 0: PRE-FLIGHT                                                │
│     └─► Verify Maestro installed: which maestro                     │
│     └─► Check simulator: xcrun simctl list devices available        │
│     └─► Read mobile-topology.md for project config                  │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 1: PLAN (First Iteration Only)                               │
│     └─► EnterPlanMode                                               │
│     └─► Explore: app structure, .maestro/ tests, recent commits     │
│     └─► ExitPlanMode                                                │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 2: FIX-VERIFY LOOP                                           │
│     └─► Run Maestro smoke: maestro test .maestro/journeys/J2-*.yaml │
│     └─► If pass: Update checkpoint, stop                            │
│     └─► If fail: Diagnose, fix code, lint, re-run tests             │
├─────────────────────────────────────────────────────────────────────┤
│  PHASE 3: COMPLETE                                                  │
│     └─► Commit: git commit -m "mobileappfix: [description]"         │
│     └─► Create checkpoint with honest booleans                      │
│     └─► Stop (hook validates checkpoint)                            │
└─────────────────────────────────────────────────────────────────────┘
```

## Minimum Smoke Test

**J2-returning-user-login.yaml is the required minimum.**

```bash
# Always run this first
maestro test .maestro/journeys/J2-returning-user-login.yaml

# Full suite if time permits
maestro test .maestro/suite.yaml
```

## Common Commands

```bash
# Maestro
maestro test <file>           # Run test
maestro hierarchy             # Debug testIDs
maestro studio                # Visual builder

# Simulator
xcrun simctl boot "iPhone 15 Pro"
open -a Simulator

# Metro
npm start --reset-cache       # Clear bundler cache
npm run ios                   # Build and run

# After native changes
npm run prebuild:clean && cd ios && pod install && cd ..
```

## Completion Checkpoint

Before stopping, create `.claude/completion-checkpoint.json`:

```json
{
  "self_report": {
    "code_changes_made": true,
    "maestro_tests_passed": true,
    "maestro_tests_passed_at_version": "abc1234",
    "linters_pass": true,
    "linters_pass_at_version": "abc1234",
    "is_job_complete": true
  },
  "reflection": {
    "what_was_done": "Fixed auth guard timing, login flow works",
    "what_remains": "none"
  },
  "evidence": {
    "maestro_flows_tested": ["J2-returning-user-login.yaml"],
    "platform": "ios",
    "device": "iPhone 15 Pro Simulator"
  }
}
```

<reference path="references/checkpoint-schema.md" />

## Maestro Artifacts

Save test evidence to `.claude/maestro-smoke/`:

```bash
mkdir -p .claude/maestro-smoke
cp -r .maestro/screenshots/* .claude/maestro-smoke/ 2>/dev/null || true
```

<reference path="references/maestro-smoke-contract.md" />

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `TEST_USER_EMAIL` | Yes | E2E test user |
| `MAESTRO_TEST_PASSWORD` | Yes | E2E test password |
| `ANDROID_HOME` | For Android | SDK path |

## Exit Conditions

| Condition | Result |
|-----------|--------|
| All booleans true, `what_remains: "none"` | SUCCESS - stop allowed |
| Any required boolean false | BLOCKED - continue working |
| Missing credentials | ASK USER (once) |

## Reference Files

| Reference | Purpose |
|-----------|---------|
| [mobile-topology.md](references/mobile-topology.md) | Project config, devices, test commands |
| [checkpoint-schema.md](references/checkpoint-schema.md) | Full checkpoint field reference |
| [maestro-smoke-contract.md](references/maestro-smoke-contract.md) | Artifact schema |
| [debugging-rubric.md](references/debugging-rubric.md) | Mobile-specific troubleshooting |
| [validation-tests-contract.md](references/validation-tests-contract.md) | Fix-specific test requirements |
