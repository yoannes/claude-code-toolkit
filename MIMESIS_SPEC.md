# Mimesis Multi-Agent Architecture Specification

## Executive Summary

This specification defines a multi-repo agent coordination system where a central manager agent orchestrates multiple project agents through file-based IPC. The design prioritizes crash-safety, auditability, and backwards compatibility with existing Claude Code infrastructure.

---

## Part A: Design Principles

### Core Strengths

| Element | Rationale |
|---------|-----------|
| **File-based IPC** | No network dependencies, auditable, crash-safe |
| **Atomic write pattern** (tmp + rename) | Prevents partial reads, well-tested pattern |
| **Two-layer classification** (explicit + heuristic) | Pragmatic; handles forgotten tags gracefully |
| **Separation of status events vs SKILL.md** | Clean concern separation; events are transient, skills are stable |
| **Append-only event trail** | Time-travel debugging, complete audit |
| **SQLite for indexing** | Battle-tested, embedded, good for read-heavy |
| **Doc-refresh as separate subagent** | Keeps stop hook fast; heavy work is conditional |

---

## Part B: Architecture

### Directory Structure

```
repo/
  .claude/                          # Preserve existing
    settings.json
    MEMORIES.md
    status.<session_id>.md          # Keep for backwards compat

  .mimesis/                         # New coordination layer
    SKILL.md                        # Project context

    status/
      current.json                  # Atomic snapshot
      sequence                      # Monotonic counter file
      events/
        YYYY-MM-DD/
          HH-MM-SS.sss_<event_id>.json

    commands/
      pending/                      # Manager writes here
      claimed/                      # Agent moves here atomically
      completed/                    # Agent moves here when done

    locks/
      agent.lock                    # PID + timestamp + heartbeat

    schemas/
      status-v1.0.schema.json
      command-v1.0.schema.json

    projections/                    # Computed views
      summary.json
```

### Event Schema

Two-tier schema to balance verbosity with auditability:

**Tier 1: Minimal (small tasks, 80% of events)**
```json
{
  "v": "1.0",
  "t": "complete",
  "s": "Fixed typo in README",
  "ts": "2026-01-11T12:34:56Z"
}
```

**Tier 2: Full (big tasks, on-demand)**
```json
{
  "v": "1.0",
  "id": "evt-uuid",
  "seq": 1234,
  "ts": "2026-01-11T12:34:56.789Z",
  "project": "project-a",
  "agent": "claude-code",
  "run": "run-8f3c",

  "type": "complete",
  "size": "big",
  "doc_refresh": true,

  "summary": "Implemented X, refactored Y",

  "stats": {
    "files": 14,
    "loc": [420, 110],
    "tests": [128, 0, 3]
  },

  "links": ["docs/api.md", ".mimesis/artifacts/report.txt"],

  "deps": {
    "requires": [],
    "blocks": []
  },

  "next": ["Update migration guide"],

  "sig": "hmac-sha256:..."
}
```

### SKILL.md Template

```markdown
# Project Name — SKILL

## Auto-Generated (do not edit)
<!-- mimesis:auto-start -->
Stack: Python 3.11, FastAPI, PostgreSQL
Files: 234 (.py: 180, .md: 32, other: 22)
Dependencies: 45 (see requirements.txt)
Last commit: abc123 (2026-01-11)
<!-- mimesis:auto-end -->

## Business Context
**Purpose**: [Human-written]
**Users**: [Human-written]
**Success metrics**: [Human-written]

## Domain Rules
- Rule 1: ...
- Invariants: ...

## Task Classification
**BIG if**: API change, schema change, >10 files, >300 LOC
**SMALL if**: <5 files, <80 LOC, no public surface changes

## Documentation Map
- `docs/architecture.md` — system design
- `docs/api.md` — endpoints

## Priorities
- P0: ...
- P1: ...

## Invariants (Machine-Verifiable)
```yaml
invariants:
  - command: "make test"
    expected_exit: 0
    description: "All tests pass"

  - file_exists: "docs/api.md"
    description: "API docs present"
```

## Validation
```bash
make test && make lint
```
```

---

## Part C: Critical Design Decisions

### 1. Namespace Strategy

**Decision**: Extend `.claude/` namespace rather than create parallel `.mimesis/`.

**Rationale**:
- Existing monitoring tools expect `.claude/status.*.md`
- Hooks (stop-validator.py, status-working.py) already write to `.claude/`
- Creates confusion to have two status file systems

**Implementation**:
- Keep `.claude/status.<session_id>.md` for backwards compatibility
- Add `.claude/mimesis/` for coordination-specific files
- Bridge pattern during migration: dual-write to both formats

### 2. Concurrency Model

**Problem**: Undefined behavior when multiple managers or agents interact.

**Solution**: Explicit locking with claim/complete flow:

```
.mimesis/
  locks/
    project-a.lock          # PID + timestamp + heartbeat
  commands/
    pending/                 # Manager writes here
    claimed/                 # Agent moves here atomically
    completed/               # Agent moves here when done
```

Lock file format:
```json
{
  "pid": 12345,
  "started": "2026-01-11T12:00:00Z",
  "heartbeat": "2026-01-11T12:34:56Z",
  "agent": "claude-code",
  "session": "abc123"
}
```

Stale lock detection: If `heartbeat` > 60s old, lock is considered abandoned.

### 3. File Watching Reliability

**Problem**: `watchdog` (inotify/FSEvents) unreliable in Docker, NFS, WSL.

**Solution**: Hybrid approach:
- Primary: File watching for responsiveness
- Fallback: Polling every 5s as heartbeat
- Health check: Manager writes `.mimesis/manager.heartbeat`

```python
class HybridWatcher:
    def __init__(self):
        self.last_poll = time.time()
        self.watcher = FileWatcher()

    def check(self):
        # Always poll if watcher might have missed events
        if time.time() - self.last_poll > 5:
            self.poll_all()
            self.last_poll = time.time()

        # Also process watcher events
        return self.watcher.get_events()
```

### 4. Authentication/Authorization

**Problem**: Any process can write to `.mimesis/commands/`.

**Solution**: HMAC signatures on command files:

```json
{
  "command": "run_tests",
  "args": {},
  "issued_at": "2026-01-11T12:34:56Z",
  "sig": "hmac-sha256:abc123..."
}
```

- Manager generates per-session secret via `MIMESIS_SECRET` env var
- Agents verify signature before executing
- Unsigned commands are rejected and logged

### 5. SKILL.md Maintenance

**Problem**: Manual maintenance leads to drift and inconsistency.

**Solution**: Hybrid auto-generated + human-curated sections:

```python
def update_skill_md(repo_path):
    skill = load_skill_md(repo_path)

    # Auto-generate sections
    skill.stack = detect_stack(repo_path)
    skill.files = count_files(repo_path)
    skill.dependencies = parse_deps(repo_path)
    skill.last_commit = get_head_sha(repo_path)

    # Compute hash for staleness detection
    auto_hash = hash(skill.auto_section)
    skill.metadata['auto_hash'] = auto_hash

    # Preserve human sections
    save_skill_md(repo_path, skill)
```

Staleness detection: Compare `auto_hash` against current repo state.

### 6. Version Migration

**Problem**: Schema changes break backwards compatibility.

**Solution**: Semantic versioning with compatibility rules:

- `1.x` = backwards compatible within major version
- Manager advertises supported versions
- Agents select highest common version
- Schema registry in `.mimesis/schemas/`

```json
{
  "v": "1.2",
  "compat": ["1.0", "1.1", "1.2"],
  "required_fields": ["v", "ts", "type"],
  "optional_fields": ["stats", "deps", "sig"]
}
```

### 7. Rate Limiting

**Problem**: Runaway agent could spam events, fill disk.

**Solution**: Multi-layer throttling:

```python
class EventThrottle:
    MAX_EVENTS_PER_SEC = 1
    MAX_QUEUE_SIZE = 1000
    MAX_DIR_SIZE_MB = 100

    def can_emit(self):
        if self.events_this_second >= self.MAX_EVENTS_PER_SEC:
            self.buffer_locally()
            return False
        if self.queue_size >= self.MAX_QUEUE_SIZE:
            self.drop_oldest()
        if self.dir_size_mb >= self.MAX_DIR_SIZE_MB:
            self.alert_and_rotate()
        return True
```

### 8. Manager Resilience

**Problem**: Manager crash leaves system in undefined state.

**Solution**: Heartbeat + catch-up mechanism:

```python
class Manager:
    HEARTBEAT_INTERVAL = 30

    def write_heartbeat(self):
        with atomic_write('.mimesis/manager.heartbeat') as f:
            json.dump({
                'ts': now(),
                'last_event_seq': self.last_processed_seq,
                'checkpoint': self.checkpoint_id
            }, f)

    def on_restart(self):
        heartbeat = load_heartbeat()
        events = load_events_since(heartbeat['last_event_seq'])
        for event in events:
            self.process(event)
```

Agents detect stale heartbeat (>90s) and operate in "degraded mode" (local-only).

### 9. Cross-Project Dependencies

**Problem**: No way to express inter-project dependencies.

**Solution**: Add dependency fields to event schema:

```json
{
  "deps": {
    "requires": ["project-b:tests-pass"],
    "blocks": ["project-c:deploy"]
  },
  "transaction_id": "tx-001"
}
```

Manager maintains dependency graph, waits for all `requires` before proceeding.

### 10. Stale Read Prevention

**Problem**: Reading `current.json` during write could get inconsistent data.

**Solution**: Sequence numbers + atomic operations:

```python
def read_current():
    while True:
        seq_before = read_file('.mimesis/status/sequence')
        data = read_file('.mimesis/status/current.json')
        seq_after = read_file('.mimesis/status/sequence')

        if seq_before == seq_after:
            return data
        # Retry if sequence changed during read
```

Write side:
```python
def write_current(data):
    seq = increment_sequence()
    data['seq'] = seq
    atomic_write('.mimesis/status/current.json', data)
```

### 11. Graceful Degradation

**Problem**: Parse errors in SKILL.md could crash manager.

**Solution**: Required vs optional fields with defaults:

```python
SKILL_SCHEMA = {
    'required': ['business_context'],
    'optional': {
        'task_classification': DEFAULT_CLASSIFICATION,
        'priorities': [],
        'invariants': []
    }
}

def load_skill(path):
    try:
        skill = parse_skill_md(path)
        validate_required(skill, SKILL_SCHEMA['required'])
        return fill_defaults(skill, SKILL_SCHEMA['optional'])
    except ParseError as e:
        log.warning(f"SKILL.md parse error: {e}")
        return DEFAULT_SKILL
```

### 12. Capability-Based Commands

**Problem**: Manager could invoke undefined agent behaviors.

**Solution**: Agents declare capabilities on startup:

```json
{
  "agent_id": "project-a-agent",
  "capabilities": ["run_tests", "deploy_staging", "refresh_docs"],
  "capabilities_version": "2026-01-11"
}
```

Manager validates commands against declared capabilities before issuing.

---

## Part D: Advanced Features

### 1. Git-Native Event Storage

Alternative to file-based events using git refs:

```bash
# Write event
git notes add -m '{"type":"complete",...}' HEAD

# Read events for commit range
git log --notes --pretty=format:"%H %N" main..HEAD
```

**Benefits**:
- Events travel with commits (push/pull)
- Built-in deduplication
- Atomic with git operations
- Free versioning

### 2. Event Sourcing with Projections

Maintain computed views for O(1) queries:

```
.mimesis/
  projections/
    project-status.json      # Current status per project
    agent-activity.json      # Last 10 actions per agent
    pending-docs.json        # All projects needing doc refresh
```

Manager updates projections on each event. Queries never scan event log.

### 3. Bloom Filter for Doc Impact Detection

Fast, probabilistic check for documentation changes:

```python
def build_doc_filter(repo_path):
    doc_filter = BloomFilter(expected_items=1000, fp_rate=0.01)
    for doc in glob(repo_path / "docs/**/*.md"):
        doc_filter.add(hash(doc.read_bytes()))
    return doc_filter

def needs_doc_refresh(changed_files, doc_filter):
    for f in changed_files:
        if f in doc_filter:
            return True  # Might need doc refresh
    return False
```

### 4. Observable SKILL.md

Self-verification metadata:

```yaml
---
skill_version: "2026-01-11"
last_verified: "2026-01-10T15:30:00Z"
repo_hash_at_verification: "abc123"
auto_sections_hash: "def456"
---
```

Manager detects: "SKILL.md was verified against `abc123`, but HEAD is `xyz789` — skill may be stale."

### 5. Distributed Consensus Lite

For critical operations requiring multiple agents to agree:

```json
{
  "command": "deploy_production",
  "requires_quorum": true,
  "votes_needed": 2,
  "current_votes": [
    {"agent": "project-a", "vote": "ready", "at": "..."},
    {"agent": "project-b", "vote": "pending", "at": "..."}
  ]
}
```

Manager waits for all votes to be "ready" before proceeding.

---

## Part E: Implementation Phases

### Phase 1: Foundation (Preserve Compatibility)
- [ ] Create `.mimesis/` directory structure
- [ ] Keep existing `.claude/status.*.md` working
- [ ] Add event writing to stop-validator.py (dual-write)
- [ ] Create minimal SKILL.md template

### Phase 2: Manager (Read-Only)
- [ ] `projects.yaml` registry
- [ ] Hybrid file-watch + polling ingester
- [ ] SQLite indexer with projections
- [ ] Query API: `get_project_status()`, `get_recent_events()`

### Phase 3: Robustness
- [ ] Lock files for concurrency
- [ ] HMAC signatures for commands
- [ ] Rate limiting (1 event/sec/agent)
- [ ] Heartbeat + catch-up mechanism

### Phase 4: Doc-Refresh Subagent
- [ ] Trigger on `complete + big`
- [ ] Conditional invocation
- [ ] Emit `docrefresh` event

### Phase 5: Commands (Write Capability)
- [ ] Capability registration
- [ ] Command queue with claim/complete flow
- [ ] Quorum voting for critical operations

---

## Verification Checklist

- [ ] Existing `.claude/status.*.md` monitoring still works
- [ ] Manager can ingest events from 3+ projects simultaneously
- [ ] Agent crash doesn't corrupt state (atomic writes verified)
- [ ] File watching falls back to polling in Docker
- [ ] SKILL.md validation errors don't crash manager
- [ ] Rate limiting prevents disk exhaustion
- [ ] HMAC signature verification blocks unsigned commands

---

## Appendix: Reference Implementations

### Atomic Write Helper

```python
import os
import tempfile

def atomic_write(path, data):
    """Write data to path atomically using rename."""
    dir_path = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)
    except:
        os.unlink(tmp_path)
        raise
```

### Event Emitter

```python
import json
import uuid
from datetime import datetime

class EventEmitter:
    def __init__(self, project, agent, run_id):
        self.project = project
        self.agent = agent
        self.run_id = run_id
        self.seq = self._load_sequence()

    def emit(self, event_type, size, summary, **kwargs):
        self.seq += 1
        event = {
            'v': '1.0',
            'id': f'evt-{uuid.uuid4().hex[:8]}',
            'seq': self.seq,
            'ts': datetime.utcnow().isoformat() + 'Z',
            'project': self.project,
            'agent': self.agent,
            'run': self.run_id,
            'type': event_type,
            'size': size,
            'summary': summary,
            **kwargs
        }
        self._write_event(event)
        return event

    def _write_event(self, event):
        date_dir = datetime.utcnow().strftime('%Y-%m-%d')
        filename = f"{datetime.utcnow().strftime('%H-%M-%S.%f')}_{event['id']}.json"
        path = f'.mimesis/status/events/{date_dir}/{filename}'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, json.dumps(event, indent=2))
        self._save_sequence()
```

### Lock Manager

```python
import json
import os
import time

class LockManager:
    STALE_THRESHOLD = 60  # seconds

    def __init__(self, lock_path):
        self.lock_path = lock_path

    def acquire(self, agent_id, session_id):
        if self._is_locked():
            if not self._is_stale():
                return False
            # Stale lock, take over

        lock_data = {
            'pid': os.getpid(),
            'started': datetime.utcnow().isoformat() + 'Z',
            'heartbeat': datetime.utcnow().isoformat() + 'Z',
            'agent': agent_id,
            'session': session_id
        }
        atomic_write(self.lock_path, json.dumps(lock_data))
        return True

    def heartbeat(self):
        if os.path.exists(self.lock_path):
            lock_data = json.loads(open(self.lock_path).read())
            lock_data['heartbeat'] = datetime.utcnow().isoformat() + 'Z'
            atomic_write(self.lock_path, json.dumps(lock_data))

    def release(self):
        if os.path.exists(self.lock_path):
            os.unlink(self.lock_path)

    def _is_stale(self):
        if not os.path.exists(self.lock_path):
            return True
        lock_data = json.loads(open(self.lock_path).read())
        heartbeat = datetime.fromisoformat(lock_data['heartbeat'].rstrip('Z'))
        age = (datetime.utcnow() - heartbeat).total_seconds()
        return age > self.STALE_THRESHOLD
```
