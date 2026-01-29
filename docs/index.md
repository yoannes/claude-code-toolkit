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
6 parallel Opus agents (3 dynamic + 3 fixed: Critical Reviewer, Architecture Advisor, Shipping Engineer) → **self-educate via codebase + web + vendor docs** → tech-stack aware (Next.js, PydanticAI, Azure) → structured disagreements → adversarial dialogue → principles over rubrics.

---

## All Slash Commands (11 commands + 3 core skills)

| Command | Purpose |
|---------|---------|
| `/godo` | Autonomous task execution |
| `/appfix` | Autonomous debugging |
| `/heavy` | Multi-agent analysis |
| `/qa` | Architecture audit |
| `/deslop` | AI slop detection |
| `/docupdate` | Documentation gaps |
| `/config-audit` | Environment variable analysis |
| `/webtest` | Browser testing |
| `/mobiletest` | Maestro E2E tests |
| `/mobileaudit` | Vision-based UI audit |
| `/interview` | Requirements Q&A |
| `/weboptimizer` | Performance benchmarking |
| `/designimprove` | UI improvement |
| `/uximprove` | UX improvement |

## All Skills (17 active, 2 deprecated)

| Skill | Triggers |
|-------|----------|
| `godo` | /godo, "go do", "just do it", "execute this" |
| `appfix` | /appfix, "fix the app", "debug production" |
| `heavy` | /heavy, "heavy analysis", "multiple perspectives", "debate this" |
| `mobileappfix` | Mobile app debugging, Maestro tests |
| `skill-sandbox` | /skill-sandbox, "test skill", "sandbox test" |
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
| `revonc-eas-deploy` | /eas, /revonc-deploy, "deploy to testflight", "build ios/android" |

### Deprecated Skills

| Skill | Status | Redirect |
|-------|--------|----------|
| `skill-tester` | Deprecated | → skill-sandbox |
| `skilltest` | Deprecated | → skill-sandbox |

## Registered Hooks (18 scripts)

| Event | Scripts | Purpose |
|-------|---------|---------|
| SessionStart | auto-update, session-snapshot, read-docs-reminder | Init and toolkit update |
| UserPromptSubmit | skill-state-initializer, read-docs-trigger | State files and doc suggestions |
| PreToolUse (*) | pretooluse-auto-approve | Auto-approve during autonomous mode |
| PreToolUse (Edit/Write) | plan-mode-enforcer | Block until plan done |
| PreToolUse (Bash) | deploy-enforcer, azure-command-guard | Block deploys, guard Azure CLI |
| PreToolUse (WebSearch) | exa-search-enforcer | Remind to use Exa MCP instead |
| PostToolUse (Edit/Write) | checkpoint-invalidator | Reset stale flags |
| PostToolUse (Bash) | bash-version-tracker, doc-updater-async | Track versions, suggest doc updates |
| PostToolUse (ExitPlanMode) | plan-mode-tracker, plan-execution-reminder | Mark plan done, inject context |
| PostToolUse (Skill) | skill-continuation-reminder | Continue loop after skill |
| Stop | stop-validator | Validate checkpoint |
| PermissionRequest | permissionrequest-auto-approve | Auto-approve during autonomous mode |

---

## Deep Dives

| Document | Description |
|----------|-------------|
| [Commands](concepts/commands.md) | How slash commands work |
| [Skills](concepts/skills.md) | How skills auto-trigger |
| [Hooks](concepts/hooks.md) | Hook lifecycle |
| [Architecture](architecture.md) | System design |
| [Appfix Guide](skills/appfix-guide.md) | Complete debugging guide |
| [Godo Guide](skills/godo-guide.md) | Autonomous task execution guide |
| [Philosophy](philosophy.md) | Core philosophy and principles |
| [Settings Reference](reference/settings.md) | Configuration options |
| [Azure Command Guard](hooks/azure-command-guard.md) | Azure CLI security hook |
| [Azure Guard Testing](hooks/azure-guard-testing.md) | Testing the Azure guard |

## Directory Structure

```
prompts/
├── config/
│   ├── settings.json      # Hook definitions
│   ├── commands/          # 11 skill definition files (+ 3 skill-commands)
│   ├── hooks/             # Python/bash hooks (18 registered)
│   └── skills/            # 17 skills (+ 2 deprecated)
├── docs/                  # Documentation
├── scripts/               # install.sh, doctor.sh
└── README.md
```
