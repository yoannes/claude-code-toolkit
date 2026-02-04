---
name: loopimprove
description: Run any prompt N times with fresh context. Each iteration is a new Claude session. Use for "/loopimprove" or run "claude-loop" from terminal.
---

# /loopimprove

Run a prompt N times, each with completely fresh context. Automates the "run, clear, run again" workflow.

## Usage

From terminal (recommended):
```bash
claude-loop "/improve improve the UX" 5
claude-loop "/improve fix accessibility" 10
```

Or invoke directly (single iteration only):
```
/loopimprove improve the button styling
```

## How It Works

The `claude-loop` script runs `claude -p "your prompt"` in a loop. Each iteration:
- Starts a **fresh Claude session** (no memory of prior iterations)
- Runs the full prompt to completion
- Moves to next iteration

This is exactly like manually doing `/clear` + running the prompt again.

## Installation

```bash
# Add to PATH (one-time setup)
ln -sf ~/.claude/scripts/claude-loop /usr/local/bin/claude-loop
```

## Examples

```bash
# Improve UX 5 times
claude-loop "/improve improve the UX of the user flow" 5

# Fix accessibility issues 3 times
claude-loop "/improve fix accessibility issues" 3

# Run burndown 10 times
claude-loop "/burndown src/components" 10
```

## Why Fresh Context?

After ~30 min of work, context fills up with:
- Failed attempts
- Intermediate states
- Stale reasoning

Fresh context each iteration:
- Re-evaluates from first principles
- No anchoring to prior decisions
- Often finds improvements the previous pass missed
