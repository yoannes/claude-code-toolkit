# Session Memories

## Source of Truth

**This repo (`namshub`) is the source of truth for all skills, hooks, and configuration.**

`~/.claude/skills/`, `~/.claude/hooks/`, and `~/.claude/CLAUDE.md` are symlinks to this repo's `config/` directory. When you edit skills, hooks, or CLAUDE.md (including via `~/.claude/`), you're editing this repo. **Always commit changes to preserve them.**

### Global CLAUDE.md

`config/CLAUDE.md` is symlinked to `~/.claude/CLAUDE.md` and read by Claude Code at session start in ALL repos. It sets global tool preferences (e.g., Exa MCP over WebSearch). The `exa-search-enforcer` hook hard-blocks WebSearch as a backstop.

---

## Memory System v5 (2026-02-01)

**Cross-session learning** via append-only event store in `~/.claude/memory/{project-hash}/events/`.

- **Auto-capture**: Checkpoint requires `key_insight` (>30 chars), `search_terms` (2-7 concept keywords), `category` enum, optional `problem_type` (controlled vocabulary), optional `core_assertions` (max 5), and optional `memory_that_helped` (event IDs) — archived on every successful stop
- **Two-layer crash safety**: PreCompact (before compaction) + Stop (clean exit)
- **Auto-injection**: Top 5 relevant events injected at SessionStart via 2-signal scoring (entity overlap 50%, recency 50%) with entity gate (zero-overlap events rejected outright)
- **Core assertions**: Persistent `<core-assertions>` block injected before memories — topic-based dedup (last-write-wins), LRU eviction at 20, compaction at SessionStart
- **Problem-type encoding**: Controlled vocabulary (`race-condition`, `config-mismatch`, `api-change`, `import-resolution`, `state-management`, `crash-safety`, `data-integrity`, `performance`, `tooling`, `dependency-management`) — auto-injected as concept entity for cross-session retrieval
- **Entity matching**: Multi-tier (exact basename 1.0, stem 0.6, concept 0.5, substring 0.35, dir 0.3) using max() not average()
- **Gradual freshness curve**: Linear ramp 1.0→0.5 over 48h, then exponential decay (half-life 7d), continuous at boundary
- **Dedup**: Prefix-hash guard (8-event lookback, 60-min window) prevents duplicates
- **Mid-session recall**: 8 recalls/session, 30s cooldown, file-locked injection log
- **Manual capture**: `/compound` skill for deep LESSON/PROBLEM/CAUSE/FIX documentation

See [docs/index.md](../docs/index.md#memory-system-v5) for full details.

---

## Architectural Decisions

### Status File Enforcement (2026-01-09, updated)
**Decision**: Two-phase enforcement - checklist visibility AND status blocking.

**Why**: Need both: (1) Full checklist always shown on first stop, (2) Status file actually enforced before allowing stop.

**Implementation**:
- First stop: Show full checklist with status as item 0 (if failed)
- Second stop: Check status again - block if still stale, allow if fresh
- This ensures checklist is never bypassed AND status is always enforced

### Change-Type Detection Filtering (2026-01-09)
**Decision**: Three-layer filtering to reduce false positives in stop-validator pattern detection.

**Why**: Patterns like `.filter(`, `.all()`, `datetime` are too generic - they match CSS, JS array methods, docs, and even the hook script itself.

**Implementation**:
1. Exclude paths: `hooks/`, `.claude/`, `node_modules/`
2. Only analyze changed lines (`+`/`-`), not diff context
3. File-extension aware: ORM patterns → `.py` only, link/websocket → `.js/.ts/.tsx` only
