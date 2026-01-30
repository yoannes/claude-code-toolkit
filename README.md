# Claude Code Toolkit

**The agent that actually finishes.**

Claude Code stops when *you* hit enter. This toolkit adds a stop hook that blocks completion until the job passes a checkpoint. No more "I've made the changes" without verification.

## Try It (60 seconds)

```bash
git clone https://github.com/Motium-AI/claude-code-toolkit.git
cd claude-code-toolkit && ./scripts/install.sh
# Restart Claude Code, then:
```

```
> /forge add a logout button to the navbar
```

Watch what happens:
1. Plans the change (parallel agents debate approach)
2. Implements it
3. Runs linters, fixes errors
4. Commits and pushes
5. Opens browser, verifies the button works
6. **Only then can it stop**

If step 5 fails, it loops back. You get working code, not promises.

## Three Skills

**`/forge`** - Task execution with verification. Give it a task, get working code.

**`/repair`** - Debugging loop. Detects web vs mobile, collects logs, fixes, deploys, verifies. Loops until healthy.

**`/heavy`** - Analysis before decisions. Spawns parallel agents with opposing views, surfaces real disagreements.

## How the Stop Hook Works

When Claude tries to stop, the hook checks a checkpoint:

```
is_job_complete: true?
linters_pass: true?
deployed: true?
web_testing_done: true?
```

All must be true. If not, Claude is blocked and must continue.

This is the difference between "done" and *actually done*.

## What This Won't Do

- Replace your judgment on architecture decisions
- Work without your codebase context (it reads your files)
- Guarantee zero bugs (it verifies, but edge cases exist)

## Documentation

Full reference, hook system details, and skill guides: [docs/index.md](docs/index.md)

## License

MIT - see [LICENSE](LICENSE)
