# Claude Code Toolkit Reference

## Quick Links

- [README](../README.md) — Overview and quick start
- [Installation](../QUICKSTART.md) — Setup guide
- [Customization](guides/customization.md) — Create your own extensions

---

## The Three Core Skills

### `/godo` — Universal Task Execution
**Use when**: You have a task and want autonomous execution.
```
/godo add a logout button to the navbar
```
Explores codebase → implements → lints → commits → deploys → verifies in browser → **cannot stop until done**.

### `/appfix` — Autonomous Debugging
**Use when**: Something is broken.
```
/appfix
```
Health checks → collects logs → diagnoses → fixes → deploys → **loops until healthy**.

### `/heavy` — Multi-Perspective Analysis
**Use when**: Complex question needing broad perspectives.
```
/heavy Should we use microservices or monolith?
```
6 parallel Opus agents → synthesis → 2-3 deep-dives → structured answer with confidence levels.

---

## All Commands (11)

| Command | Purpose |
|---------|---------|
| `/godo` | Autonomous task execution |
| `/appfix` | Autonomous debugging |
| `/heavy` | Multi-agent analysis |
| `/qa` | Architecture audit |
| `/deslop` | AI slop detection |
| `/docupdate` | Documentation gaps |
| `/webtest` | Browser testing |
| `/interview` | Requirements Q&A |
| `/weboptimizer` | Performance benchmarking |
| `/designimprove` | UI improvement |
| `/uximprove` | UX improvement |

## All Skills (14)

| Skill | Triggers |
|-------|----------|
| `godo` | /godo, "go do", "just do it" |
| `appfix` | /appfix, "fix the app", "debug production" |
| `heavy` | /heavy, "heavy analysis", "multiple perspectives" |
| `toolkit` | /toolkit, "update toolkit" |
| `deploy-pipeline` | /deploy, deployment questions |
| `webapp-testing` | Browser testing |
| `frontend-design` | Web UI development |
| `async-python-patterns` | asyncio, concurrent |
| `nextjs-tanstack-stack` | Next.js, TanStack |
| `prompt-engineering-patterns` | Prompt optimization |
| `ux-designer` | UX design |
| `design-improver` | UI review |
| `ux-improver` | UX review |
| `docs-navigator` | Documentation |

## Hook Events (7)

| Event | Scripts | Purpose |
|-------|---------|---------|
| SessionStart | auto-update, session-snapshot, read-docs-reminder | Init |
| UserPromptSubmit | skill-state-initializer, read-docs-trigger | State files |
| PreToolUse (Edit/Write) | plan-mode-enforcer | Block until plan done |
| PostToolUse (Edit/Write) | checkpoint-invalidator | Reset stale flags |
| PostToolUse (Bash) | bash-version-tracker | Track versions |
| PostToolUse (ExitPlanMode) | plan-execution-reminder | Inject context |
| PermissionRequest | appfix-auto-approve | Auto-approve |
| Stop | stop-validator | Validate checkpoint |

---

## Deep Dives

| Document | Description |
|----------|-------------|
| [Commands](concepts/commands.md) | How slash commands work |
| [Skills](concepts/skills.md) | How skills auto-trigger |
| [Hooks](concepts/hooks.md) | Hook lifecycle |
| [Architecture](architecture.md) | System design |
| [Appfix Guide](skills/appfix-guide.md) | Complete debugging guide |

## Directory Structure

```
prompts/
├── config/
│   ├── settings.json      # Hook definitions
│   ├── commands/          # 11 commands
│   ├── hooks/             # Python hooks
│   └── skills/            # 14 skills
├── docs/                  # Documentation
├── scripts/               # install.sh, doctor.sh
└── README.md
```
