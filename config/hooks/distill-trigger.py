#!/usr/bin/env python3
"""
SessionStart Hook - Distillation Daemon Trigger

Checks raw/ for unprocessed transcripts from previous sessions.
For each (up to 3), extracts a digest and creates a task file.
Outputs hookSpecificOutput suggesting background Sonnet agent spawn.

Pattern: Same as doc-updater-async.py (hook is fast detector/suggester,
LLM work done by Task() agent spawned by Claude in background).

Part of the Compound Memory System that enables cross-session learning.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add hooks directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))

from _common import log_debug

DISTILLATION_PROMPT = """TRANSCRIPT DISTILLATION TASK

You are extracting reusable learnings from a previous Claude Code session.

WORKING DIRECTORY: {cwd}
TRANSCRIPT: {transcript_filename}

SESSION DIGEST:
---
{digest}
---

YOUR TASK:
1. Read the session digest above
2. Identify 1-5 reusable LESSON memories (or 0 if none exist)
3. Create events by calling the CLI script via Bash

WHAT MAKES A GOOD LESSON:
- Reusable insight about a specific tool, API, or pattern
- Bug fix revealing a non-obvious root cause
- Configuration discovery useful for future sessions
- Architecture decision with clear rationale
- Error pattern paired with its solution

WHAT TO SKIP:
- Session logistics ("read the docs", "started by...")
- Trivial file operations with no insight
- One-off tasks with no reusable knowledge
- Common knowledge that any developer would know

FOR EACH LESSON, run this Bash command (adjust content/entities/category):

echo '{{"cwd": "{cwd}", "transcript": "{transcript_filename}", "lessons": [
  {{
    "content": "LESSON: <one-sentence insight>\\nCONTEXT: <2-3 sentences of supporting detail>",
    "entities": ["<affected-file.py>", "<concept-keyword>"],
    "category": "<bugfix|pattern|config|architecture|tooling>"
  }}
]}}' | python3 "$HOME/.claude/hooks/distill-create-event.py"

ENTITY GUIDELINES:
- Include file paths affected (e.g., "hooks/_memory.py", "settings.json")
- Include concept keywords (e.g., "crash-safety", "dedup", "atomic-write")
- 3-7 entities per lesson, lowercase for concepts
- File entities should use the basename or parent/basename format

IF NO LEARNINGS EXIST (research/exploration/trivial session):
echo '{{"cwd": "{cwd}", "transcript": "{transcript_filename}", "lessons": []}}' | python3 "$HOME/.claude/hooks/distill-create-event.py"

IMPORTANT: Always call the CLI script exactly once, even if lessons=[] (to mark transcript as processed).
"""


def _create_task_file(cwd: str, transcript_path: Path, digest: str) -> str:
    """Create a task file for the background Sonnet agent."""
    task_dir = Path(cwd) / ".claude" / "async-tasks"
    task_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = transcript_path.stem[-6:] if len(transcript_path.stem) > 6 else transcript_path.stem
    task_file = task_dir / f"distill-{timestamp}-{suffix}.json"

    task = {
        "type": "transcript-distillation",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "pending",
        "transcript_filename": transcript_path.name,
        "cwd": cwd,
        "instructions": DISTILLATION_PROMPT.format(
            cwd=cwd,
            transcript_filename=transcript_path.name,
            digest=digest,
        ),
    }

    task_file.write_text(json.dumps(task, indent=2))
    return str(task_file)


def main():
    input_data = json.loads(sys.stdin.read() or "{}")
    cwd = input_data.get("cwd", "")

    if not cwd:
        sys.exit(0)

    try:
        from _memory import get_raw_dir
        from _distill import (
            extract_digest,
            get_unprocessed_transcripts,
            mark_transcript_status,
            cleanup_distill_manifest,
        )
    except ImportError:
        log_debug(
            "Cannot import required modules",
            hook_name="distill-trigger",
        )
        sys.exit(0)

    raw_dir = get_raw_dir(cwd)

    # Cleanup stale manifest entries
    try:
        cleanup_distill_manifest(raw_dir)
    except Exception:
        pass

    # Find unprocessed transcripts
    unprocessed = get_unprocessed_transcripts(raw_dir)
    if not unprocessed:
        sys.exit(0)

    log_debug(
        f"Found {len(unprocessed)} unprocessed transcript(s)",
        hook_name="distill-trigger",
    )

    # Process each: extract digest + create task file
    task_files: list[tuple[str, str]] = []
    for transcript_path in unprocessed:
        digest = extract_digest(transcript_path)
        if not digest or len(digest) < 50:
            mark_transcript_status(raw_dir, transcript_path.name, "skipped")
            log_debug(
                f"Skipped {transcript_path.name}: too short",
                hook_name="distill-trigger",
            )
            continue

        task_file = _create_task_file(cwd, transcript_path, digest)
        mark_transcript_status(raw_dir, transcript_path.name, "in-progress")
        task_files.append((task_file, transcript_path.name))

    if not task_files:
        sys.exit(0)

    # Output suggestion for spawning background Sonnet agents
    suggestions = []
    for task_file, transcript_name in task_files:
        suggestions.append(
            f"Task(\n"
            f'  description="Distill learnings from {transcript_name}",\n'
            f'  subagent_type="general-purpose",\n'
            f'  model="sonnet",\n'
            f"  run_in_background=true,\n"
            f'  prompt="Read the task file at {task_file} and follow the instructions field to extract memory events."\n'
            f")"
        )

    context = (
        f"TRANSCRIPT DISTILLATION: {len(task_files)} unprocessed transcript(s) from previous sessions.\n"
        f"Spawn background agent(s) to extract learnings:\n\n"
        + "\n\n".join(suggestions)
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }

    log_debug(
        "Suggesting distillation agents",
        hook_name="distill-trigger",
        parsed_data={"task_count": len(task_files)},
    )

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
